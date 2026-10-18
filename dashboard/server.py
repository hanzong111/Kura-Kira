"""Kura-Kira dashboard: a read-only web view of the ledger (stdlib only).

    python3 -m dashboard.server                       # http://127.0.0.1:8790, DUIT_DB / DUIT_CONFIG as usual
    DUIT_DB=data/demo.db python3 -m dashboard.server  # the demo month from dashboard/seed_demo.py

    GET /api/status?month=YYYY-MM     cards: buckets, week allowance, fixed bills, paid-by, balance, questions
    GET /api/spends?month=&person=&bucket=&category=&paid_by=&q=     table rows + top places
    GET /api/spends.csv?...           the same rows as CSV
    GET /api/events                   SSE: "change" whenever the ledger file is written

All numbers come from duit.ledger / duit.report; this file only shapes them for the page and formats money
with duit.money.fmt. A fresh SQLite connection is opened per request (WAL lets the bot write meanwhile).
Binds to 127.0.0.1 and rejects non-localhost Host headers (DNS-rebinding guard): the ledger is private.
KURA_KIRA_HOSTS=a.example,b.example also accepts those names, for a tunnel that puts a login in front.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import mimetypes
import os
import time
from contextlib import contextmanager
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from duit import config, db
from duit.backfill import PLACE as BACKFILL_PLACE
from duit.ledger import EACH, Ledger, LedgerError, norm_place
from duit.money import fmt
from duit.periods import month_bounds, month_key

WEB = Path(__file__).resolve().parent / "web"
HOST, PORT = "127.0.0.1", 8790
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
# keys whose integer values are sen; each gets a "<key>_fmt" sibling in the JSON
MONEY = {"cap", "spent", "left", "amount", "allowance", "target", "carry", "total", "spends", "fixed", "unknown",
         "unsorted", "outflow_plan", "total_sen", "share"}
CSV_COLUMNS = ["Date", "Day", "Who", "Place", "Item", "Bucket", "Category", "Amount", "Split", "Paid by"]


def cell(text: str) -> str:
    """Chat text in a CSV cell: a leading = + - @ would run as a spreadsheet formula, so quote it."""
    return f"'{text}" if text[:1] in ("=", "+", "-", "@") else text


def add_fmt(obj, currency: str):
    """Recursively add `<key>_fmt` next to every money field."""
    if isinstance(obj, list):
        return [add_fmt(v, currency) for v in obj]
    if not isinstance(obj, dict):
        return obj
    out = {}
    for k, v in obj.items():
        out[k] = add_fmt(v, currency)
        if k in MONEY and isinstance(v, int) and not isinstance(v, bool):
            out[f"{k}_fmt"] = fmt(v, currency)
    return out


class App:
    """Everything the handler needs; tests build one with their own DB, config and clock."""

    def __init__(self, db_path: str | os.PathLike | None = None, config_path: str | os.PathLike | None = None,
                 clock: Callable[[], datetime] | None = None, hosts: tuple[str, ...] = ()):
        self.db_path = Path(db_path) if db_path else db.default_path()
        # Host headers accepted besides localhost, e.g. the ngrok domain (the tunnel does the login)
        self.hosts = LOCAL_HOSTS + tuple(h.strip().lower() for h in hosts if h.strip())
        self.config_path = config_path
        self.clock = clock

    @contextmanager
    def ledger(self):
        conn = db.connect(self.db_path)
        try:
            yield Ledger(conn, config.load(self.config_path), self.clock)
        finally:
            conn.close()

    # ---- read helpers that the ledger doesn't have (plain reads, no money maths) -------------------
    @staticmethod
    def months(ledger: Ledger) -> list[str]:
        """Months with spends or a plan, plus the current month, newest first."""
        rows = ledger.conn.execute(
            "SELECT DISTINCT substr(spent_on, 1, 7) FROM entries WHERE deleted_at IS NULL "
            "UNION SELECT DISTINCT month FROM plans").fetchall()
        return sorted({r[0] for r in rows} | {month_key(ledger.today())}, reverse=True)

    def _month(self, ledger: Ledger, value: str | None) -> str:
        month = value or month_key(ledger.today())
        try:
            month_bounds(month)
        except ValueError:
            raise LedgerError(f"month must be YYYY-MM, got {value!r}") from None
        # status() creates a month's plan rows on first use; don't let a URL create empty months
        if month not in self.months(ledger):
            raise LedgerError(f"no data for {month}")
        return month

    # ---- endpoints ---------------------------------------------------------------------------------
    def status(self, params: dict) -> dict:
        with self.ledger() as ledger:
            cfg = ledger.cfg
            month = self._month(ledger, params.get("month"))
            st = ledger.status(month)
            first, last = month_bounds(month)
            today = ledger.today()
            pending = []
            for p in st["pending"]:
                e = ledger.entry(p["id"])
                options = [cfg.buckets[b].label if b in cfg.buckets else b for b in (e["bucket_options"] or [])]
                pending.append({**p, "sender_name": cfg.people[p["sender"]].name,
                                "who": self._who(cfg, e["shares"]), "options": options,
                                "split": self._split(cfg, e["shares"]) if len(e["shares"]) > 1 else ""})
            st["pending"] = pending
            st.update({
                "day": min(max((today - first).days + 1, 0), last.day), "days": last.day,
                "months": self.months(ledger),
                "people_order": list(cfg.people),
                "bucket_order": [{"key": k, "label": b.label, "kind": b.kind}
                                 for k, b in cfg.buckets_in(month).items()],
                "categories": list(cfg.categories),
            })
            return add_fmt(st, cfg.currency)

    @staticmethod
    def _who(cfg, shares: dict) -> str:
        people = [p for p, a in shares.items() if a > 0] or list(shares)
        return "Both" if len(people) == len(cfg.people) > 1 else " + ".join(cfg.people[p].name for p in people)

    @staticmethod
    def _split(cfg, shares: dict) -> str:
        return " · ".join(f"{cfg.people[p].name} {fmt(a, cfg.currency)}" for p, a in shares.items())

    def spends(self, params: dict) -> dict:
        with self.ledger() as ledger:
            cfg = ledger.cfg
            month = self._month(ledger, params.get("month"))
            person = params.get("person") or None
            rows = ledger.list_entries(month, person=person, bucket=params.get("bucket") or None,
                                       category=params.get("category") or None,
                                       paid_by=params.get("paid_by") or None, query=params.get("q") or None)
            pkey = cfg.person(person).key if person else None
            out = []
            for e in rows:
                d = date.fromisoformat(e["spent_on"])
                b = cfg.buckets.get(e["bucket"]) if e["bucket"] else None
                paid = e["paid_by"]
                row = {
                    "id": e["id"], "spent_on": e["spent_on"], "date": f"{d.day} {d:%b}", "day": DAYS[d.weekday()],
                    "who": self._who(cfg, e["shares"]), "place": e["place"], "item": e["item"] or "",
                    "bucket": e["bucket"], "bucket_label": b.label if b else "Unsorted",
                    "category": e["category"] or "", "total_sen": e["total_sen"],
                    "split": self._split(cfg, e["shares"]) if len(e["shares"]) > 1 else "",
                    "paid_by": paid,
                    "paid_by_label": "?" if paid is None else ("Each paid own" if paid == EACH
                                                               else cfg.people[paid].name),
                    "needs": e["needs"],
                }
                if pkey:
                    row["share"] = e["shares"].get(pkey, 0)
                out.append(row)

            amount_of = (lambda r: r["share"]) if pkey else (lambda r: r["total_sen"])
            places: dict[str, dict] = {}
            for r in out:
                if r["place"] == BACKFILL_PLACE:
                    continue  # placeholders for days before tracking aren't a real place
                p = places.setdefault(norm_place(r["place"]) or r["place"],
                                      {"place": r["place"], "bucket": r["bucket"], "count": 0, "total": 0})
                p["count"] += 1
                p["total"] += amount_of(r)
            top = sorted(places.values(), key=lambda p: (-p["total"], p["place"]))[:6]
            return add_fmt({"month": month, "person": pkey, "rows": out, "count": len(out),
                            "total": sum(amount_of(r) for r in out), "top_places": top}, cfg.currency)

    def spends_csv(self, params: dict) -> tuple[str, str]:
        data = self.spends(params)
        buf = io.StringIO()
        w = csv.writer(buf)
        share_col = [f"{data['person'].title()} share"] if data["person"] else []
        w.writerow(CSV_COLUMNS + share_col)
        for r in reversed(data["rows"]):  # oldest first reads better in a spreadsheet
            w.writerow([r["spent_on"], r["day"], r["who"], cell(r["place"]), cell(r["item"]), r["bucket_label"],
                        cell(r["category"]), f"{r['total_sen'] / 100:.2f}", r["split"], r["paid_by_label"]]
                       + ([f"{r['share'] / 100:.2f}"] if data["person"] else []))
        name = f"kura-kira-{data['month']}" + (f"-{data['person']}" if data["person"] else "") + ".csv"
        return buf.getvalue(), name

    def signature(self) -> tuple:
        """Changes whenever the bot writes: WAL appends to -wal, checkpoints touch the main file."""
        sig = []
        for p in (self.db_path, Path(f"{self.db_path}-wal")):
            try:
                s = p.stat()
                sig.append((s.st_mtime_ns, s.st_size))
            except FileNotFoundError:
                sig.append(None)
        return tuple(sig)


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "KuraKira/1"

        def log_message(self, *a):  # quiet
            pass

        def host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            return host in app.hosts

        def send_body(self, body: bytes, ctype: str, code: int = 200, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, obj, code: int = 200):
            self.send_body(json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8", code)

        def do_GET(self):
            if not self.host_ok():
                return self.send_json({"error": "forbidden host"}, 403)
            u = urlparse(self.path)
            params = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if u.path == "/api/status":
                    return self.send_json(app.status(params))
                if u.path == "/api/spends":
                    return self.send_json(app.spends(params))
                if u.path == "/api/spends.csv":
                    text, name = app.spends_csv(params)
                    return self.send_body(text.encode(), "text/csv; charset=utf-8",
                                          extra={"Content-Disposition": f'attachment; filename="{name}"'})
                if u.path == "/api/events":
                    return self.events()
            except (LedgerError, ValueError) as e:
                return self.send_json({"error": str(e)}, 400)
            return self.static(u.path)

        def static(self, path: str):
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            f = (WEB / rel).resolve()
            if WEB not in f.parents or not f.is_file():
                return self.send_json({"error": "not found"}, 404)
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
                ctype += "; charset=utf-8"
            self.send_body(f.read_bytes(), ctype)

        def events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last, quiet = app.signature(), 0.0
            try:
                self.wfile.write(b"retry: 3000\nevent: hello\ndata: {}\n\n")
                self.wfile.flush()
                while True:
                    time.sleep(1)
                    sig = app.signature()
                    if sig != last:
                        last, quiet = sig, 0.0
                        self.wfile.write(b"event: change\ndata: {}\n\n")
                        self.wfile.flush()
                    else:
                        quiet += 1
                        if quiet >= 15:  # keep-alive; also notices a closed tab
                            quiet = 0.0
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


def serve(app: App, host: str = HOST, port: int = PORT) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    return httpd


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=int(os.environ.get("KURA_KIRA_PORT", PORT)))
    ap.add_argument("--db", help="ledger file (default: DUIT_DB or data/duit.db)")
    args = ap.parse_args()
    app = App(args.db, hosts=tuple(os.environ.get("KURA_KIRA_HOSTS", "").split(",")))
    httpd = serve(app, HOST, args.port)
    print(f"Kura-Kira dashboard on http://localhost:{args.port}  (ledger {app.db_path})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

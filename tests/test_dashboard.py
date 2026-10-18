import csv
import io
import json
import threading
import urllib.error
import urllib.request

import pytest

from dashboard.seed_demo import seed
from dashboard.server import App, serve


@pytest.fixture
def base(tmp_path, cfg, clock):
    path = tmp_path / "demo.db"
    seed(path, clock.now.strftime("%Y-%m-%dT%H:%M")).conn.close()
    httpd = serve(App(path, clock=clock), port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", path
    httpd.shutdown()
    httpd.server_close()


def get(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=5) as r:
        return r.status, r.headers, r.read().decode()


def get_json(url):
    return json.loads(get(url)[2])


def error(url, headers=None):
    with pytest.raises(urllib.error.HTTPError) as e:
        get(url, headers)
    return e.value.code, json.loads(e.value.read())


def test_status_cards(base):
    url, _ = base
    st = get_json(f"{url}/api/status")
    assert st["month"] == "2026-10" and (st["day"], st["days"]) == (17, 31)
    assert st["months"] == ["2026-10", "2026-09"]
    hanz, vanisa = st["people"]["hanz"], st["people"]["vanisa"]
    toll = hanz["buckets"]["toll"]
    # Hanz paid both toll reloads (RM53), but toll is shared: half of it is Vanisa's cost
    assert (toll["spent"], toll["cap"], toll["status"]) == (2650, 5000, "ok")
    assert toll["left_fmt"] == "RM23.50" and toll["cap_fmt"] == "RM50.00"
    weekday = hanz["buckets"]["weekday"]
    assert (weekday["cap_fmt"], weekday["target_fmt"]) == ("RM440.00", "RM100.00")
    week = vanisa["buckets"]["weekend"]["week"]  # she overspent the 10-11 Oct weekend
    assert (week["target_fmt"], week["carry_fmt"], week["allowance_fmt"]) == ("RM200.00", "-RM81.00", "RM119.00")
    assert (hanz["buckets"]["house"]["status"], hanz["buckets"]["car"]["status"]) == ("paid", "due")
    assert vanisa["buckets"]["car"]["paid"] and vanisa["unsorted_fmt"] == "RM75.00"
    assert st["combined"]["goals"]["cap_fmt"] == "RM5,300.00"  # Oct: 4.4 weekday + 4.5 weekend targets
    assert st["balance"]["owes"] == {"from": "vanisa", "to": "hanz", "amount": 1940, "amount_fmt": "RM19.40"}
    assert st["paid"]["unknown_fmt"] == "RM69.70"
    assert [(t["on"], t["from"], t["to"], t["amount_fmt"]) for t in st["paid"]["transfers"]] == [
        ("2026-10-06", "vanisa", "hanz", "RM40.00")]
    rows = {r["bucket"]: r for r in st["paid"]["rows"]}
    assert rows["toll"]["people"]["hanz"]["amount_fmt"] == "RM53.00" and rows["toll"]["people"]["vanisa"]["amount"] == 0
    for k in st["people_order"]:  # the breakdown adds up to each person's total
        assert sum(r["people"][k]["amount"] for r in st["paid"]["rows"]) == st["paid"]["people"][k]["total"]
    q = {p["place"]: p for p in st["pending"]}
    assert q["Nando's"]["needs"] == ["payer"] and q["Nando's"]["who"] == "Both"
    assert q["Watsons"]["options"] == ["Chu Chu / Toiletries", "Extra"]


def test_status_other_month_and_bad_month(base):
    url, _ = base
    sep = get_json(f"{url}/api/status?month=2026-09")
    assert sep["day"] == 30 and "week" not in sep["people"]["hanz"]["buckets"]["weekday"]
    assert error(f"{url}/api/status?month=2030-01") == (400, {"error": "no data for 2030-01"})
    assert error(f"{url}/api/status?month=oct")[0] == 400


def test_spends_filters(base):
    url, _ = base
    all_rows = get_json(f"{url}/api/spends?month=2026-10")
    assert all_rows["count"] == 32 and all_rows["rows"][0]["spent_on"] == "2026-10-17"
    zap = get_json(f"{url}/api/spends?q=zapfan&paid_by=hanz")
    split = next(r for r in zap["rows"] if r["split"])
    assert split["who"] == "Both" and split["split"] == "Hanz RM13.20 · Vanisa RM14.50"
    assert split["day"] == "Thu" and split["date"] == "15 Oct"
    unsorted = get_json(f"{url}/api/spends?bucket=unsorted")
    assert [r["place"] for r in unsorted["rows"]] == ["Watsons"]
    assert unsorted["rows"][0]["bucket_label"] == "Unsorted" and unsorted["rows"][0]["needs"] == ["bucket"]
    food = get_json(f"{url}/api/spends?category=food&person=vanisa")
    assert food["person"] == "vanisa" and all(r["category"] == "Food" for r in food["rows"])
    assert error(f"{url}/api/spends?person=bob")[0] == 400


def test_person_filter_shows_their_share(base):
    url, _ = base
    d = get_json(f"{url}/api/spends?person=hanz&bucket=weekday")
    nandos = next(r for r in d["rows"] if r["place"] == "Nando's")
    assert (nandos["total_sen"], nandos["share"], nandos["share_fmt"]) == (6970, 3850, "RM38.50")
    assert nandos["paid_by_label"] == "?"
    # the table total for one person matches the ledger's own bucket total
    st = get_json(f"{url}/api/status")
    assert d["total"] == st["people"]["hanz"]["buckets"]["weekday"]["spent"]


def test_top_places(base):
    url, _ = base
    top = get_json(f"{url}/api/spends")["top_places"]
    assert top[0] == {"place": "Parents", "bucket": "parents", "count": 2, "total": 100000, "total_fmt": "RM1,000.00"}
    sushi = next(p for p in top if p["place"] == "Sushi-Mentai")
    assert (sushi["count"], sushi["total"]) == (3, 21700)


def test_csv_export(base):
    url, _ = base
    status, headers, body = get(f"{url}/api/spends.csv?person=vanisa&q=zapfan")
    assert status == 200 and headers["Content-Type"].startswith("text/csv")
    assert "kura-kira-2026-10-vanisa.csv" in headers["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(body)))
    assert rows[0][-1] == "Vanisa share" and len(rows) == 4
    assert rows[-1][0] == "2026-10-15" and rows[-1][7] == "27.70" and rows[-1][-1] == "14.50"


def test_csv_cells_cannot_be_formulas(base, cfg, clock):
    from duit import db
    from duit.ledger import Ledger

    url, path = base
    conn = db.connect(path)
    Ledger(conn, cfg, clock).log_spend(sender="hanz", place="=HYPERLINK(\"x\")", total=5, bucket="daily")
    conn.close()
    rows = list(csv.reader(io.StringIO(get(f"{url}/api/spends.csv?q=HYPERLINK")[2])))
    assert rows[1][3] == "'=HYPERLINK(\"x\")"


def test_static_and_guards(base):
    url, _ = base
    status, headers, body = get(f"{url}/")
    assert status == 200 and "duit/css/duit.css" in body
    with urllib.request.urlopen(f"{url}/duit/assets/sprites/hanz/hanz-sheet.png", timeout=5) as r:
        assert r.headers["Content-Type"] == "image/png" and r.read(4) == b"\x89PNG"
    assert get(f"{url}/duit/css/duit.css")[1]["Content-Type"].startswith("text/css")
    assert error(f"{url}/../duit/ledger.py")[0] == 404
    assert error(f"{url}/api/status", {"Host": "evil.example"})[0] == 403


def test_events_fire_on_write_not_on_reads(base, cfg, clock):
    from duit import db
    from duit.ledger import Ledger

    url, path = base
    before = App(path).signature()
    get(f"{url}/api/status")  # dashboard reads must not look like a change
    get(f"{url}/api/spends")
    assert App(path).signature() == before
    with urllib.request.urlopen(f"{url}/api/events", timeout=5) as stream:
        assert stream.readline().startswith(b"retry:")
        assert stream.readline() == b"event: hello\n"
        stream.readline(), stream.readline()
        Ledger(db.connect(path), cfg, clock).log_spend(sender="hanz", place="Kopi Corner", total=5, bucket="daily")
        assert stream.readline() == b"event: change\n"


def test_extra_hosts_for_a_tunnel(tmp_path, clock):
    seed(tmp_path / "d.db", clock.now.strftime("%Y-%m-%dT%H:%M")).conn.close()
    httpd = serve(App(tmp_path / "d.db", clock=clock, hosts=("Kura.ngrok-free.dev", "")), port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{httpd.server_port}/api/status"
        assert get(url, {"Host": "kura.ngrok-free.dev"})[0] == 200
        assert error(url, {"Host": "other.ngrok-free.dev"})[0] == 403
    finally:
        httpd.shutdown()
        httpd.server_close()

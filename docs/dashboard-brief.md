# Dashboard brief (Phase 2)

Build the local web dashboard for Kura-Kira, the couple spending tracker in this repo. Read `README.md` and
`docs/PLAN.md` first.

## Where to work
- Use a separate git worktree so you don't collide with the agent work happening in `~/duit`:
  `git -C ~/duit worktree add ~/duit-dashboard -b feat/dashboard`
- Put everything under `dashboard/` in that worktree. **Don't change `duit/*.py`.** If you need something
  from the ledger that doesn't exist, add a read-only helper in `dashboard/`, or write down what you need in
  your final report.
- Commit on `feat/dashboard` with Conventional Commit messages. Don't push and don't merge into `main`.

## Data (read-only)
- The ledger is SQLite at `~/duit/data/duit.db` (env `DUIT_DB`). The config is `config.toml`, falling back to
  `config.example.toml` (env `DUIT_CONFIG`).
- Use the existing Python API, never your own SQL maths:
  - `from duit import config, db; from duit.ledger import Ledger`
  - `Ledger(db.connect(), config.load()).status("2026-10")` returns everything for the cards: per-person
    buckets with cap/spent/left/status, week allowance, fixed paid/due, unsorted, combined totals, paid-by
    totals, balance and pending questions.
  - `ledger.list_entries(month, person, bucket, category, paid_by, query)` returns the spending table rows
    (place, item, category, bucket, total_sen, shares, paid_by, spent_on, needs).
- Money is integer sen. Format it with `duit.money.fmt`.
- The real DB may be empty. Write `dashboard/seed_demo.py`, which fills a separate demo DB
  (`data/demo.db`) through `Ledger.log_spend` / `pay_fixed` / `settle` with a realistic month: the example
  rows in `docs/design-prompt.md`, one bucket over budget, one Unsorted entry, one entry with no payer and a
  split Zapfan lunch. Run the dashboard with `DUIT_DB=data/demo.db` while developing.

## Server
- Python stdlib only (`http.server`/`ThreadingHTTPServer`), the same as `~/kopitiam/server.py`. No new
  dependencies.
- Serve on `127.0.0.1:8790`.
- `GET /api/status?month=YYYY-MM` and `GET /api/spends?month=&person=&bucket=&category=&paid_by=&q=`
  return JSON, with `GET /api/spends.csv` for the CSV export.
- Live refresh: either the browser polls every 3 s, or SSE that fires when the DB file's mtime changes.
- Read-only for now. The "Needs answer" box only shows the questions; answering happens in Telegram.
- Open SQLite connections per request; WAL is on, so the bot can write at the same time.

## Layout (the agreed plan; a ChatGPT design will replace the visuals later)
1. **Header:** "KURA-KIRA", month picker, "day 17/31".
2. **COMBINED card** (full width):
   - one big goals bar ("RM3,120 / RM5,020") with a pace marker at the month-elapsed %
   - one small bar per bucket
   - House/Car as PAID/DUE stamps, not bars
   - paid-by strip (Hanz paid vs Vanisa paid) and "Vanisa owes Hanz RMx"
3. **HANZ (left) | VANISA (right)**, mirrored:
   - "This week": weekday and weekend bars showing allowance/spent/left
   - "This month": the total, then bars for extra, grocery, chuchu, petrol, toll and parents
   - House/Car stamps; Vanisa is always PAID, Hanz is DUE until paid
   - an Unsorted chip
4. **Needs answer** box listing the pending questions.
5. **Spending table:**
   - filters: month, who, bucket, category, paid by, search
   - columns: Date, Day, Who, Place/item, Bucket, Category, Amount, Split, Paid by
   - when filtered to one person, show that person's share
   - "Top places" side panel, CSV button
   - clicking a bucket bar filters the table
6. **Status colours:** `ok` green, `ahead` yellow, `over` red (from `status` in the API).
7. **Phone width (390px):** the cards stack, and the table turns into cards. No horizontal scroll.

## Look
- For now, the Kopitiam pixel style from `~/kopitiam/web/pixel.css`: cream/coffee/teal tokens, gold/red
  stripe trim, 4px hard shadows, no rounded corners, monospace numbers.
- Keep every colour and font in CSS variables in one file (`dashboard/web/theme.css`). Keep sprites/icons
  under `dashboard/web/assets/`. The visuals are being redesigned in ChatGPT and will be swapped in later,
  so the theme must be replaceable without touching the layout code.

## Always-on hosting
- Add a systemd **user** service `kura-kira-dashboard.service` (in `dashboard/`, plus an install script
  that symlinks it into `~/.config/systemd/user/`, runs `systemctl --user enable --now`, and points
  `DUIT_DB` at the real `~/duit/data/duit.db`). It should start at login and restart on failure.
- Final link: http://localhost:8790

## Done means
- `seed_demo.py` plus the server run, and the page shows the layout above with the demo data on desktop and
  at 390px. Check this with headless Playwright from `~/.hermes/hermes-agent/node_modules/playwright` and
  attach screenshots.
- Tests in `tests/test_dashboard.py` for the API endpoints (they run with `./scripts/test.sh`).
- The service is installed, and `curl -s localhost:8790/api/status` works.
- A final report: what was built, screenshots, how to run it, and any ledger helpers you'd like added.

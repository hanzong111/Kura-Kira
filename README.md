# duit

Spending tracker for two. A Hermes agent sits in a Telegram group; whenever one of us spends money we
post it (`Sushi-Mentai (food) : 56.50`, `zapfan, lunch, RM13.20 hanz, 14.50 vanisa, Hanz paid`) and the
agent records it against our monthly plan. A pixel-themed dashboard shows combined and per-person progress.

**Principle:** the LLM only reads the message and calls a tool. This SQLite ledger stores everything and
does all the maths: totals, weekly allowances, pace, balances. The model never adds up money itself.

## Status

| Step | Part | State |
|---|---|---|
| 1 | Ledger + tests (`duit/`) | done |
| 2 | MCP tools for the agent | next |
| 3 | Parsing test set; check sender ID reaches the agent | |
| 4 | Hermes `duit` profile + Telegram group | |
| 5 | Cron: alerts, Sunday recap, month-end report | |
| 6 | Trial week | |
| 7 | Dashboard (Kopitiam pixel theme) | |

The full plan is in [docs/PLAN.md](docs/PLAN.md).

## Layout

```
duit/config.py   plan: people, budget buckets, rules (from config.toml)
duit/money.py    amounts as integer sen; parsing, splitting
duit/periods.py  months, Mon-Sun weeks, weekly allowance
duit/db.py       SQLite schema
duit/ledger.py   all writes: log_spend, resolve, edit, undo, settle, pay_fixed, set_plan
duit/report.py   all reads: bucket status, pace, balance, paid totals, pending questions
```

## Run

```bash
cp config.example.toml config.toml   # then fill in Telegram user IDs
python3 -m pip install pytest
python3 -m pytest -q
python3 -m duit status               # month overview in the terminal
```

Data lives in `data/duit.db` (gitignored). Override with `DUIT_DB` / `DUIT_CONFIG`.

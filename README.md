# Kura-Kira

Spending tracker for two. **Kura-Kira**, a Hermes agent, sits in a Telegram group; whenever one of us spends money we
post it (`Sushi-Mentai (food) : 56.50`, `zapfan, lunch, RM13.20 hanz, 14.50 vanisa, Hanz paid`) and the
agent records it against our monthly plan. A pixel-themed dashboard shows combined and per-person progress.

**Principle:** the LLM only reads the message and calls a tool. This SQLite ledger stores everything and
does all the maths: totals, weekly allowances, pace, balances. The model never adds up money itself.

## Status

| Step | Part | State |
|---|---|---|
| 1 | Ledger + tests (`duit/`) | done |
| 2 | Agent tools as a Hermes plugin (`duit/tools.py`, `hermes/plugin/duit`) | done |
| 3 | Parsing test set (`eval/`) + agent rules (`hermes/SOUL.md`) | built; needs a Codex login to run |
| 4 | Hermes `kura-kira` profile + Telegram group | profile created; Telegram next |
| 5 | Cron: alerts, Sunday recap, month-end report | |
| 6 | Trial week | |
| 7 | Dashboard (Kopitiam pixel theme) | prototype on `feat/dashboard` (`dashboard/`) |

The full plan is in [docs/PLAN.md](docs/PLAN.md).

## Layout

```
duit/config.py   plan: people, budget buckets, rules (from config.toml)
duit/money.py    amounts as integer sen; parsing, splitting
duit/periods.py  months, Mon-Sun weeks, weekly allowance
duit/db.py       SQLite schema
duit/ledger.py   all writes: log_spend, resolve, edit, undo, settle, pay_fixed, set_plan
duit/report.py   all reads: bucket status, pace, balance, paid totals, pending questions
duit/replies.py  chat text (confirmations, questions, alerts, status) built from ledger numbers
duit/tools.py    the agent's tools: JSON schemas + dispatcher; sender/chat/message come from the gateway
hermes/plugin/   Hermes plugin that registers the tools (toolset `duit`)
hermes/SOUL.md   the agent's rules
eval/            parsing test set run against the real agent
```

## Run

```bash
cp config.example.toml config.toml   # then fill in Telegram user IDs
./scripts/test.sh -q                 # creates .venv on first run
.venv/bin/python -m duit status      # month overview in the terminal
.venv/bin/python eval/run.py         # parsing test set against the live agent
```

Hermes profile `kura-kira` (in `~/.hermes/profiles/kura-kira/`):

- `plugins/duit` -> symlink to `hermes/plugin/duit`, enabled with `plugins.enabled: [duit]`
- `SOUL.md` -> symlink to `hermes/SOUL.md`
- `platform_toolsets: {telegram: [duit], cli: [duit]}` so the bot has the ledger tools and nothing else
- model `openai-codex` (`hermes -p kura-kira auth add openai-codex` to log in)

Why a plugin and not MCP: Hermes doesn't show the model the sender's Telegram ID or the message ID,
but plugin tools can read them from the gateway's session context. So the sender is never chosen by the model.

## Dashboard

```bash
python3 -m dashboard.seed_demo                       # demo month in data/demo.db
DUIT_DB=data/demo.db python3 -m dashboard.server     # http://localhost:8790
dashboard/install-service.sh                         # always-on user service on the real ledger
```

Read-only, stdlib only. `dashboard/server.py` serves `/api/status`, `/api/spends`, `/api/spends.csv` and
`/api/events` (SSE on ledger writes). The look is the DUIT Co-op Arcade pack: its runtime files (fonts, sprites,
icons, `duit.css`) are in `dashboard/web/duit/`, and the handoff, reference mockup and source art are in
`docs/design/duit-arcade/`. `dashboard/web/app.css` only adds what the dashboard needs on top.

Data lives in `data/duit.db` (gitignored). Override with `DUIT_DB` / `DUIT_CONFIG`.

import json
from datetime import date

import pytest

from duit import jobs


def test_due_reminder_only_when_something_is_due(ledger):
    text = jobs.due_text(ledger, date(2026, 10, 1))
    assert text.splitlines()[:3] == ["⏳ Fixed bills still due for October:", "@Hanz Car RM300.00",
                                     "@Hanz House RM1,000.00"]
    ledger.pay_fixed("hanz", "house", "2026-10")
    ledger.pay_fixed("hanz", "car", "2026-10")
    assert jobs.due_text(ledger, date(2026, 10, 5)) is None


def test_weekly_recap(ledger):
    ledger.log_spend(sender="hanz", place="Zapfan", total=30, bucket="daily", spent_on="2026-10-14")
    ledger.log_spend(sender="hanz", place="Sushi Zanmai", total=230, bucket="daily", spent_on="2026-10-17")
    ledger.log_spend(sender="vanisa", place="Parents", total=500, bucket="parents", spent_on="2026-10-16")
    text = jobs.recap_text(ledger, date(2026, 10, 18))
    lines = text.splitlines()
    assert lines[0] == "📅 Week 12 Oct – 18 Oct"
    assert lines[1] == ("Hanz: Weekday RM30.00/RM100.00 (saved RM70.00) 🟩 · "
                        "Weekend RM230.00/RM200.00 (over RM30.00) 🟥")
    assert "Top this week: Sushi Zanmai RM230.00, Zapfan RM30.00" in text      # parents isn't a place
    assert "Vanisa Parents" not in text                                         # exactly on budget: no flag


def test_month_report(ledger):
    ledger.log_spend(sender="vanisa", place="Watsons", total=74, bucket="chuchu", spent_on="2026-10-18")
    text = jobs.month_text(ledger, "2026-10")
    assert text.startswith("🧾 October 2026 report card\nTogether: RM74.00 / RM5,300.00 → saved RM5,226.00 🟩")
    assert text.count("  Chu Chu / Toiletries: RM37.00/RM60.00 · RM23.00 left 🟩") == 2   # shared: half each
    assert text.endswith("Balance: Hanz owes Vanisa RM37.00")


def test_month_job_reports_last_month_early_in_the_month(ledger):
    assert jobs.run(ledger, "month", date(2026, 11, 1)).startswith("🧾 October 2026")


def test_check_job_silent_when_healthy(ledger):
    assert jobs.run(ledger, "check", date(2026, 10, 18)) is None


def test_send_posts_to_the_group(monkeypatch, cfg):
    from dataclasses import replace
    sent = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(req, timeout):
        sent.append((req.full_url, json.loads(req.data)))
        return Resp()

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setattr(jobs.urllib.request, "urlopen", fake_urlopen)
    jobs.send(replace(cfg, telegram_chat_id="-100"), "hello")
    assert sent == [("https://api.telegram.org/bot123:abc/sendMessage", {"chat_id": "-100", "text": "hello"})]


def test_token_read_from_env_file_only(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("OTHER_SECRET=nope\nexport TELEGRAM_BOT_TOKEN=\"999:xyz\"\n")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("DUIT_BOT_ENV", str(env))
    assert jobs._token_from_env_file() == "999:xyz"


def test_send_without_chat_id_refuses(cfg, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:a")
    with pytest.raises(SystemExit):
        jobs.send(cfg, "x")

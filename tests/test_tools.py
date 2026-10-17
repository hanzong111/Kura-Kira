import importlib.util
import json

import pytest

from duit import config
from duit.tools import Context, Tools, specs

HANZ, VANISA = Context(sender="hanz", chat_id="g", msg_id="1"), Context(sender="vanisa", chat_id="g", msg_id="2")


@pytest.fixture
def tools(ledger):
    return Tools(ledger)


def ctx(sender, msg):
    return Context(sender=sender, chat_id="g", msg_id=str(msg))


def test_every_spec_has_a_handler(cfg, tools):
    names = {s["name"] for s in specs(cfg)}
    assert names == set(tools._handlers)
    for s in specs(cfg):
        assert s["parameters"]["type"] == "object" and s["description"]


def test_log_spend_reply(tools):
    r = tools.call("duit_log_spend", {"place": "Sushi-Mentai", "amount": "RM56.50", "bucket": "daily",
                                      "category": "food"}, HANZ)
    assert r["reply"].startswith("✅ #1 Sushi-Mentai · Weekend · RM56.50 · Hanz — RM")
    assert r["question"] is None


def test_sender_comes_from_context_not_model(cfg, ledger):
    real = config.Config(**{**cfg.__dict__, "people": {
        "hanz": config.Person("hanz", "Hanz", 111), "vanisa": config.Person("vanisa", "Vanisa", 222)}})
    ledger.cfg = real
    t = Tools(ledger)
    r = t.call("duit_log_spend", {"place": "Lunch", "amount": 10, "bucket": "daily"},
               Context(sender_telegram_id="222", chat_id="g", msg_id="5"))
    assert "· Vanisa" in r["reply"]
    r = t.call("duit_log_spend", {"place": "x", "amount": 1}, Context(sender_telegram_id="999", msg_id="6"))
    assert "isn't from Hanz or Vanisa" in r["error"]


def test_retry_of_same_message_is_logged_once(tools, ledger):
    tools.call("duit_log_spend", {"place": "Lunch", "amount": 10, "bucket": "daily"}, HANZ)
    r = tools.call("duit_log_spend", {"place": "Lunch", "amount": 10, "bucket": "daily"}, HANZ)
    assert r["duplicate"] and r["reply"] == "Already logged as #1."


def test_several_spends_in_one_message(tools, ledger):
    tools.call("duit_log_spend", {"place": "Lunch", "amount": 12, "bucket": "daily", "part": 1}, HANZ)
    tools.call("duit_log_spend", {"place": "Petrol", "amount": 50, "bucket": "petrol", "part": 2}, HANZ)
    assert len(ledger.list_entries()) == 2


def test_split_without_payer_question_then_answer(tools):
    r = tools.call("duit_log_spend", {"place": "Zapfan", "shares": {"Hanz": 13.2, "Vanisa": "14.50"},
                                      "bucket": "daily"}, VANISA)
    q = r["question"]
    assert q["text"] == ("@Hanz @Vanisa #1 Zapfan RM27.70 (Hanz RM13.20 · Vanisa RM14.50): who paid?\n"
                         "Reply: Hanz / Vanisa / Each paid own")
    a = tools.call("duit_answer", {"entry_id": 1, "paid_by": "Hanz"}, ctx("hanz", 3))
    assert a["needs"] == [] and "paid by Hanz" in a["reply"]
    assert "Vanisa owes Hanz RM14.50" in tools.call("duit_status", {}, HANZ)["reply"]


def test_answer_without_id_needs_single_pending(tools):
    tools.call("duit_log_spend", {"place": "Decathlon", "amount": 120, "bucket_options": ["daily", "extra"]}, VANISA)
    tools.call("duit_log_spend", {"place": "Watsons", "amount": 75, "bucket_options": ["chuchu", "extra"]},
               ctx("vanisa", 9))
    r = tools.call("duit_answer", {"bucket": "daily"}, VANISA)
    assert "2 entries are waiting" in r["error"] and "#1 Decathlon" in r["error"]


def test_unsorted_question_options(tools):
    r = tools.call("duit_log_spend", {"place": "Decathlon", "amount": 120, "bucket_options": ["daily", "extra"]},
                   VANISA)
    assert r["question"]["options"] == ["Everyday (weekday/weekend)", "Extra", "Other"]
    assert r["reply"] == "✅ #1 Decathlon · ❓ Unsorted · RM120.00 · Vanisa"
    tools.call("duit_answer", {"bucket": "daily", "category": "Sport"}, ctx("vanisa", 50))
    assert tools.call("duit_lookup_place", {"name": "decathlon"}, VANISA)["place"]["category"] == "Sport"


def test_ask_extra_for_big_everyday_spend(tools):
    assert tools.call("duit_log_spend", {"place": "Uniqlo", "amount": 180, "bucket": "daily"}, HANZ)["ask_extra"]


def test_errors_come_back_as_ask(tools):
    r = tools.call("duit_log_spend", {"place": "Zapfan", "amount": 27.7, "shares": {"hanz": 13.2, "vanisa": 12}},
                   HANZ)
    assert r["ask"] is True and "add up to" in r["error"]


def test_edit_and_undo_default_to_senders_latest(tools, ledger):
    tools.call("duit_log_spend", {"place": "Petronas", "amount": 80, "bucket": "petrol"}, HANZ)
    tools.call("duit_log_spend", {"place": "Lunch", "amount": 9, "bucket": "daily"}, VANISA)
    r = tools.call("duit_edit_spend", {"amount": 85}, ctx("hanz", 3))
    assert r["reply"].startswith("✏️ #1 Petronas · Petrol · RM85.00")
    r = tools.call("duit_delete_spend", {}, ctx("hanz", 4))
    assert r["reply"] == "🗑️ Deleted #1 Petronas RM85.00"
    assert [e["place"] for e in ledger.list_entries()] == ["Lunch"]


def test_fixed_and_settle(tools):
    r = tools.call("duit_pay_fixed", {"bills": ["house", "car"]}, HANZ)
    assert r["reply"].splitlines() == ["✅ House RM1,000.00 · Hanz · Paid for October",
                                       "✅ Car RM300.00 · Hanz · Paid for October"]
    assert "already marked paid" in tools.call("duit_pay_fixed", {"bills": ["house"]}, HANZ)["reply"]
    assert tools.call("duit_fixed_due", {}, HANZ)["reply"] == "All fixed bills paid ✓"
    tools.call("duit_log_spend", {"place": "Grab", "shares": {"vanisa": 25}, "paid_by": "hanz", "bucket": "daily"},
               ctx("hanz", 7))
    r = tools.call("duit_settle_up", {"from_person": "vanisa", "to_person": "hanz"}, ctx("vanisa", 8))
    assert r["reply"] == "🤝 Vanisa → Hanz RM25.00\nBalance: all settled."


def test_status_for_me(tools):
    r = tools.call("duit_status", {"person": "me"}, VANISA)["reply"]
    assert "Vanisa:" in r and "Hanz:" not in r


def test_list_spends(tools):
    tools.call("duit_log_spend", {"place": "Sushi-Mentai", "amount": 56.5, "bucket": "daily", "category": "Food"}, HANZ)
    tools.call("duit_log_spend", {"place": "Zapfan", "shares": {"hanz": 13.2, "vanisa": 14.5}, "paid_by": "hanz",
                                  "bucket": "daily", "category": "Food"}, ctx("hanz", 5))
    r = tools.call("duit_list_spends", {"category": "food", "person": "hanz"}, HANZ)
    assert r["count"] == 2 and r["total"] == "RM69.70"


def test_plugin_registers_and_reads_session_env(monkeypatch, tmp_path):
    from duit.config import ROOT
    monkeypatch.setenv("DUIT_DB", str(tmp_path / "p.db"))
    monkeypatch.setenv("DUIT_CONFIG", str(ROOT / "config.example.toml"))
    spec = importlib.util.spec_from_file_location("duit_plugin", ROOT / "hermes/plugin/duit/__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    registered = {}

    class FakeCtx:
        def register_tool(self, name, toolset, schema, handler, **kw):
            assert toolset == "duit"
            registered[name] = handler

    mod.register(FakeCtx())
    assert "duit_log_spend" in registered
    # example config has no Telegram IDs, so any ID is a stranger
    monkeypatch.setenv("HERMES_SESSION_USER_ID", "42")
    out = json.loads(registered["duit_log_spend"]({"place": "x", "amount": 1}))
    assert "isn't from Hanz or Vanisa" in out["error"]


def test_bot_cannot_answer_its_own_question(tools):
    r = tools.call("duit_log_spend", {"place": "Jaya Grocer", "amount": 120, "shares": {"hanz": 60, "vanisa": 60},
                                      "bucket": "grocery"}, VANISA)
    assert r["needs"] == ["payer"]
    for name, args in (("duit_answer", {"entry_id": 1, "paid_by": "vanisa"}),
                       ("duit_edit_spend", {"entry_id": 1, "paid_by": "vanisa"})):
        out = tools.call(name, args, VANISA)  # same message as the spend
        assert "don't answer it yourself" in out["error"]
    assert tools.call("duit_answer", {"entry_id": 1, "paid_by": "vanisa"}, ctx("vanisa", 99))["needs"] == []

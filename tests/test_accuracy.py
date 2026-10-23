"""The model only reads; code computes. These tests pin every place a number could go wrong."""
import importlib.util
import json
from datetime import datetime, timezone

import pytest

from duit import db
from duit.integrity import backup, check
from duit.textcheck import money_numbers
from duit.tools import Context, Tools


@pytest.fixture
def tools(ledger):
    return Tools(ledger)


def msg(text, sender="hanz", msg_id="1", sent_at=None):
    return Context(sender=sender, chat_id="g", msg_id=msg_id, text=text, sent_at=sent_at)


@pytest.mark.parametrize("text,found", [
    ("lunch : RM56.50", [5650]), ("zapfan , lunch , RM13.20 hanz , 14.50 vanisa , Hanz paid", [1320, 1450]),
    ("dinner 60 split 2:1 hanz paid", [6000]), ("gsc movie 2 pax 44", [4400]), ("reach in 10 min", []),
    ("edit #142 food 30", [3000]), ("uniqlo x2 180", [18000]), ("dinner at 7pm 40", [4000]),
    ("10:30 brunch 25", [2500]), ("18/10 grab 12", [1200]), ("7-eleven 5.20", [520]),
    ("RM1,250.00 rent", [125000]), ('[Replying to Kura-Kira: "#1 Zapfan RM27.70"]\n\nhanz paid', []),
])
def test_money_numbers(text, found):
    assert money_numbers(text) == found


# ---- splits are computed by code -------------------------------------------------------------------
def test_even_split_computed_by_code(tools, ledger):
    r = tools.call("duit_log_spend", {"place": "Sushi Mentai", "amount": "80", "split": "even", "paid_by": "vanisa",
                                      "bucket": "daily"}, msg("sushi mentai 80 split, vanisa paid"))
    assert ledger.entry(r["entry_id"])["shares"] == {"hanz": 4000, "vanisa": 4000}


def test_odd_sen_split_adds_up(tools, ledger):
    r = tools.call("duit_log_spend", {"place": "Mamak", "amount": "25.01", "split": "even", "bucket": "daily"},
                   msg("mamak 25.01 shared"))
    e = ledger.entry(r["entry_id"])
    assert sum(e["shares"].values()) == 2501 and sorted(e["shares"].values()) == [1250, 1251]


def test_ratio_split_in_given_order(tools, ledger):
    r = tools.call("duit_log_spend", {"place": "Dinner", "amount": 60, "split": "2:1",
                                      "split_between": ["hanz", "vanisa"], "paid_by": "hanz", "bucket": "daily"},
                   msg("dinner 60 split 2:1 hanz paid"))
    assert ledger.entry(r["entry_id"])["shares"] == {"hanz": 4000, "vanisa": 2000}


def test_for_person(tools, ledger):
    r = tools.call("duit_log_spend", {"place": "Grab", "amount": 25, "for_person": "vanisa", "paid_by": "hanz",
                                      "category": "Transport"}, msg("grab 25 for vanisa, hanz paid"))
    e = ledger.entry(r["entry_id"])
    assert e["shares"] == {"vanisa": 2500} and e["paid_by"] == "hanz" and e["bucket"] == "weekend"


def test_only_one_split_mode(tools):
    r = tools.call("duit_log_spend", {"place": "x", "amount": 10, "split": "even", "for_person": "vanisa"}, msg("x 10"))
    assert "only one of" in r["error"]


# ---- amounts must be in the message ----------------------------------------------------------------
def test_made_up_amount_rejected(tools, ledger):
    r = tools.call("duit_log_spend", {"place": "Lunch", "amount": 56.0, "bucket": "daily"}, msg("lunch : RM56.50"))
    assert "can't find 56.00" in r["error"] and ledger.list_entries() == []


def test_computed_share_rejected(tools):
    # the model did the maths itself (40/40) instead of split: "even" -> rejected, nothing logged
    r = tools.call("duit_log_spend", {"place": "Sushi", "shares": {"hanz": 40, "vanisa": 40}},
                   msg("sushi mentai 80 split, vanisa paid"))
    assert "can't find 40.00" in r["error"]


def test_total_next_to_shares_that_dont_add_up(tools, ledger):
    # the flaky eval case: the model passed only the shares and dropped the stated total
    r = tools.call("duit_log_spend", {"place": "Zapfan", "shares": {"hanz": "13.20", "vanisa": "12.00"},
                                      "paid_by": "hanz"}, msg("zapfan 27.70 hanz 13.20 vanisa 12.00 hanz paid"))
    assert "is that the total" in r["error"] and ledger.list_entries() == []


def test_settle_and_plan_amounts_checked(tools):
    assert "can't find" in tools.call("duit_settle_up", {"from_person": "vanisa", "to_person": "hanz", "amount": 15},
                                      msg("vanisa paid hanz 14.50"))["error"]
    assert "can't find" in tools.call("duit_set_plan", {"bucket": "grocery", "amount": 300},
                                      msg("plan: grocery 250"))["error"]
    assert tools.call("duit_set_plan", {"bucket": "weekday", "amount": "25"},
                      msg("weekday 25 a day"))["reply"] == "📝 Weekday = RM25.00 per day for Hanz & Vanisa from 2026-10"


def test_no_text_means_no_check(tools):
    """CLI/tests without a message still work (nothing to check against)."""
    assert tools.call("duit_log_spend", {"place": "x", "amount": 5, "bucket": "daily"}, msg(None))["entry_id"] == 1


# ---- the model's missing bucket is filled by category ----------------------------------------------
@pytest.mark.parametrize("category,bucket", [("Leisure", "weekend"), ("Food", "weekend"), ("Groceries", "grocery"),
                                             ("Pet", "chuchu"), ("Toiletries", "chuchu")])
def test_category_fallback_bucket(tools, ledger, category, bucket):
    r = tools.call("duit_log_spend", {"place": "x", "amount": 44, "category": category}, msg("x 44"))
    assert ledger.entry(r["entry_id"])["bucket"] == bucket


def test_parents_is_a_bill_not_a_spend(tools, ledger):
    r = tools.call("duit_log_spend", {"place": "parents", "amount": 500, "category": "Family"}, msg("parents 500"))
    assert r["reply"] == "✅ Parents RM500.00 · Hanz · Paid for October"
    assert ledger.list_entries() == []


def test_options_mean_ask_not_fallback(tools, ledger):
    r = tools.call("duit_log_spend", {"place": "Decathlon", "amount": 120, "category": "Sport",
                                      "bucket_options": ["daily", "extra"]}, msg("decathlon 120"))
    assert r["needs"] == ["bucket"]


# ---- dates come from when the message was sent ------------------------------------------------------
def test_date_is_send_time_not_processing_time(tools, ledger, clock):
    friday_night = datetime(2026, 10, 16, 15, 30, tzinfo=timezone.utc)   # Fri 23:30 in KL
    clock.set("2026-10-17T09:00")                                        # processed Saturday morning
    r = tools.call("duit_log_spend", {"place": "Supper", "amount": 15, "bucket": "daily"},
                   msg("supper 15", sent_at=friday_night))
    e = ledger.entry(r["entry_id"])
    assert (e["spent_on"], e["bucket"]) == ("2026-10-16", "weekday")
    r = tools.call("duit_log_spend", {"place": "Dinner", "amount": 40, "bucket": "daily", "date": "yesterday"},
                   msg("yesterday dinner 40", msg_id="2", sent_at=friday_night))
    assert ledger.entry(r["entry_id"])["spent_on"] == "2026-10-15"


# ---- edits ------------------------------------------------------------------------------------------
def test_edit_total_keeps_people_and_proportions(tools, ledger):
    tools.call("duit_log_spend", {"place": "Grab", "amount": 25, "for_person": "vanisa", "paid_by": "hanz",
                                  "bucket": "daily"}, msg("grab 25 for vanisa hanz paid"))
    r = tools.call("duit_edit_spend", {"entry_id": 1, "amount": 28}, msg("wrong, should be 28", msg_id="2"))
    assert ledger.entry(1)["shares"] == {"vanisa": 2800}
    tools.call("duit_log_spend", {"place": "Zapfan", "shares": {"hanz": "10", "vanisa": "30"}, "paid_by": "hanz",
                                  "bucket": "daily"}, msg("zapfan 10 hanz 30 vanisa hanz paid", msg_id="3"))
    tools.call("duit_edit_spend", {"entry_id": 2, "amount": 80}, msg("edit #2 80", msg_id="4"))
    assert ledger.entry(2)["shares"] == {"hanz": 2000, "vanisa": 6000}
    assert r["reply"].startswith("✏️ **Expense updated · #1**\n\n🌤 **Grab · ")


# ---- audit, integrity, backup -----------------------------------------------------------------------
def test_every_call_is_audited(tools, ledger):
    tools.call("duit_log_spend", {"place": "Lunch", "amount": "12", "bucket": "daily"}, msg("lunch 12"))
    tools.call("duit_log_spend", {"place": "Lunch", "amount": "13"}, msg("lunch 12", msg_id="2"))
    rows = ledger.conn.execute("SELECT tool, msg_id, ok, args FROM audit ORDER BY id").fetchall()
    assert [(r["tool"], r["msg_id"], r["ok"]) for r in rows] == [("duit_log_spend", "1", 1), ("duit_log_spend", "2", 0)]
    assert json.loads(rows[1]["args"])["amount"] == "13"


def test_integrity_check_finds_corruption(tools, ledger, cfg):
    tools.call("duit_log_spend", {"place": "Zapfan", "shares": {"hanz": "13.20", "vanisa": "14.50"}, "paid_by": "hanz",
                                  "bucket": "daily"}, msg("zapfan 13.20 hanz 14.50 vanisa hanz paid"))
    assert check(ledger.conn, cfg) == []
    ledger.conn.execute("UPDATE shares SET amount_sen = 1400 WHERE person='vanisa'")
    ledger.conn.execute("UPDATE entries SET bucket='weekday'")   # it was a Saturday
    problems = check(ledger.conn, cfg)
    assert any("shares add up to 2720 sen, total is 2770" in p for p in problems)
    assert any("weekday bucket but spent on a Saturday" in p for p in problems)


def test_backup(tmp_path, cfg, clock):
    from duit.ledger import Ledger
    led = Ledger(db.connect(tmp_path / "live.db"), cfg, clock)
    led.log_spend(sender="hanz", place="A", total=10, bucket="daily")
    out = backup(led.conn, tmp_path / "backups", keep=2)
    copy = db.connect(out)
    assert copy.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 1


# ---- the plugin posts the ledger's text, not the model's ---------------------------------------------
@pytest.fixture
def plugin(monkeypatch, tmp_path):
    from duit.config import ROOT
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text((ROOT / "config.example.toml").read_text()
                        .replace('name = "Hanz"\ntelegram_id = 0', 'name = "Hanz"\ntelegram_id = 111'))
    monkeypatch.setenv("DUIT_DB", str(tmp_path / "p.db"))
    monkeypatch.setenv("DUIT_CONFIG", str(cfg_path))
    monkeypatch.setenv("HERMES_SESSION_USER_ID", "111")
    monkeypatch.setenv("HERMES_SESSION_CHAT_ID", "g")
    monkeypatch.setenv("HERMES_SESSION_MESSAGE_ID", "77")
    spec = importlib.util.spec_from_file_location("duit_plugin_t", ROOT / "hermes/plugin/duit/__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    hooks, tools_ = {}, {}

    class FakeCtx:
        def register_tool(self, name, toolset, schema, handler, **kw):
            tools_[name] = handler

        def register_hook(self, name, fn):
            hooks[name] = fn

    mod.register(FakeCtx())
    return mod, hooks, tools_


def test_plugin_replaces_model_text_with_ledger_text(plugin):
    mod, hooks, tools_ = plugin

    class Raw:
        date = datetime(2026, 10, 17, 5, 0, tzinfo=timezone.utc)

    class Event:
        message_id, text, raw_message = "77", "lunch : RM56.50", Raw()

    hooks["pre_gateway_dispatch"](event=Event())
    out = json.loads(tools_["duit_log_spend"]({"place": "lunch", "amount": "RM56.50", "bucket": "daily"}))
    assert out["entry_id"] == 1
    final = hooks["transform_llm_output"](response_text="Logged lunch RM65.50, you have RM999 left!")
    assert final == out["reply"]          # the model's (wrong) numbers never reach the chat


def test_plugin_checks_amount_against_original_text(plugin):
    mod, hooks, tools_ = plugin

    class Event:
        message_id, text, raw_message = "77", "lunch : RM56.50", None

    hooks["pre_gateway_dispatch"](event=Event())
    out = json.loads(tools_["duit_log_spend"]({"place": "lunch", "amount": "65.50", "bucket": "daily"}))
    assert "can't find 65.50" in out["error"]
    # nothing logged, so the model's question goes through untouched
    assert hooks["transform_llm_output"](response_text="How much was lunch?") is None


def test_plugin_keeps_question_after_a_refusal(plugin):
    mod, hooks, tools_ = plugin
    hooks["pre_llm_call"](user_message="lunch 12, coffee")
    tools_["duit_log_spend"]({"place": "lunch", "amount": "12", "bucket": "daily", "part": 1})
    tools_["duit_log_spend"]({"place": "coffee", "part": 2})          # no amount -> refused
    final = hooks["transform_llm_output"](response_text="How much was the coffee?")
    lines = final.splitlines()
    assert lines[:3] == ["✅ **Expense recorded · #1**", "", lines[2]] and lines[2].startswith("🗓 **Lunch · ")
    assert lines[-1] == "How much was the coffee?"


def test_named_payer_owns_a_plain_spend(tools, ledger):
    """Real bug 2026-10-18: 'Vanisa Paid RM70 (Sushi Zanmai)' sent by Hanz was charged to Hanz's budget."""
    text = "oct 17 , Hanz paid RM44 ( cafe , food ) , Vanisa Paid RM70 ( Sushi Zanmai , food )"
    tools.call("duit_log_spend", {"place": "cafe", "amount": "RM44", "paid_by": "hanz", "category": "Food",
                                  "date": "2026-10-17", "part": 1}, msg(text))
    tools.call("duit_log_spend", {"place": "Sushi Zanmai", "amount": "RM70", "paid_by": "vanisa", "category": "Food",
                                  "date": "2026-10-17", "part": 2}, msg(text))
    assert ledger.entry(1)["shares"] == {"hanz": 4400}
    assert (ledger.entry(2)["shares"], ledger.entry(2)["paid_by"]) == ({"vanisa": 7000}, "vanisa")
    assert ledger.balance()["owes"] is None
    st = ledger.status()["people"]
    assert st["hanz"]["buckets"]["weekend"]["spent"] == 4400
    assert st["vanisa"]["buckets"]["weekend"]["spent"] == 7000


def test_paying_for_someone_else_still_works(tools, ledger):
    tools.call("duit_log_spend", {"place": "Grab", "amount": 25, "for_person": "vanisa", "paid_by": "hanz",
                                  "bucket": "daily"}, msg("grab 25 for vanisa, hanz paid", sender="vanisa"))
    assert ledger.entry(1)["shares"] == {"vanisa": 2500} and ledger.balance()["owes"]["to"] == "hanz"


# ---- answers to the bot's questions are applied by code -------------------------------------------------
@pytest.mark.parametrize("reply,needs,options,expected", [
    ("Toiletries , rememebr watson = toiletries", ["bucket"], ["chuchu", "daily", "extra"],
     {"bucket": "chuchu", "category": "Toiletries"}),
    ("extra", ["bucket"], ["daily", "extra"], {"bucket": "extra"}),
    ("everyday la", ["bucket"], ["daily", "extra"], {"bucket": "daily"}),
    ("sport lah, for badminton", ["bucket"], ["daily", "extra"], None),          # unclear -> the model
    ("hanz paid", ["payer"], None, {"paid_by": "hanz"}),
    ("each paid own", ["payer"], None, {"paid_by": "each"}),
    ("I paid", ["payer"], None, {"paid_by": "vanisa"}),                          # sender is Vanisa
    ("i think hanz paid?", ["payer"], None, None),                               # ambiguous -> the model
])
def test_interpret_answers(cfg, reply, needs, options, expected):
    from duit.answers import interpret
    entry = {"needs": needs, "bucket_options": options, "deleted_at": None}
    assert interpret(cfg, entry, reply, "vanisa") == expected


def test_plugin_applies_answer_in_code_and_reasks_on_silence(plugin, monkeypatch):
    mod, hooks, tools_ = plugin
    tools = mod._get_tools()
    log = tools.call("duit_log_spend", {"place": "Vanity Box", "amount": "RM 74", "category": "Shopping",
                                        "bucket_options": ["chuchu", "daily", "extra"]},
                     Context(sender_telegram_id="111", chat_id="g", msg_id="18", text="vanity box RM 74"))
    question = log["question"]["text"]

    class Src:
        user_id, chat_id = "111", "g"

    class Answer:
        message_id, text, raw_message, source = "77", "Toiletries , remember vanity box = toiletries", None, Src()
        reply_to_is_own_message, reply_to_text = True, question

    hooks["pre_gateway_dispatch"](event=Answer())
    e = tools.led.entry(1)
    assert (e["bucket"], e["category"], e["needs"]) == ("chuchu", "Toiletries", [])
    final = hooks["transform_llm_output"](response_text="NO_REPLY")       # the model said nothing useful
    assert final.startswith("✅ **Expense recorded · #1**\n\n🐱 **Vanity Box · RM74.00**\nChu Chu / Toiletries")
    assert tools.led.lookup_place("vanity box")["bucket"] == "chuchu"       # remembered

    # an unclear reply the model also ignores -> code re-asks instead of a Hermes warning
    log2 = tools.call("duit_log_spend", {"place": "Decathlon", "amount": "120", "bucket_options": ["daily", "extra"]},
                      Context(sender_telegram_id="111", chat_id="g", msg_id="19", text="decathlon 120"))

    class Unclear(Answer):
        message_id, text, reply_to_text = "78", "hmm not sure", log2["question"]["text"]

    hooks["pre_gateway_dispatch"](event=Unclear())
    monkeypatch.setenv("HERMES_SESSION_MESSAGE_ID", "78")
    assert hooks["transform_llm_output"](response_text="NO_REPLY").startswith("Sorry, I didn't catch that. @Hanz #2")


def test_plugin_log_then_edit_posts_one_block(plugin):
    """Real bug 2026-10-23: the model logged #33 without its split, then edited it; both replies were posted."""
    mod, hooks, tools_ = plugin
    hooks["pre_llm_call"](user_message="Hanz paid RM27 , Coffee , split between vanisa and Hanz")
    tools_["duit_log_spend"]({"place": "Coffee", "amount": 27, "bucket": "daily", "paid_by": "hanz",
                              "split": "even"})
    tools_["duit_edit_spend"]({"entry_id": 1, "category": "Food"})
    final = hooks["transform_llm_output"](response_text="OK")
    assert final.count("Expense") == 1 and final.startswith("✅ **Expense recorded · #1**")
    assert "Hanz: RM13.50 · Vanisa: RM13.50" in final


def test_plugin_retry_after_refusal_posts_only_the_ledger_reply(plugin):
    mod, hooks, tools_ = plugin
    hooks["pre_llm_call"](user_message="Hanz paid RM27 , Coffee , split between vanisa and Hanz")
    assert "split" in json.loads(tools_["duit_log_spend"]({"place": "Coffee", "amount": 27, "paid_by": "hanz"}))["error"]
    tools_["duit_log_spend"]({"place": "Coffee", "amount": 27, "paid_by": "hanz", "split": "even"})
    final = hooks["transform_llm_output"](response_text="OK")
    assert final.count("Expense") == 1 and not final.endswith("OK")


def test_split_word_without_split_is_refused(tools, ledger):
    r = tools.call("duit_log_spend", {"place": "Coffee", "amount": 27, "paid_by": "hanz"},
                   msg("Hanz paid RM27 , Coffee , split between vanisa and Hanz"))
    assert r["ask"] and "split" in r["error"] and not ledger.list_entries()
    # several amounts: "split" may be about another one, so it's not second-guessed
    r = tools.call("duit_log_spend", {"place": "lunch", "amount": 12, "part": 1}, msg("lunch 12, dinner 40 split"))
    assert not r.get("error")
    # shared buckets split themselves
    r = tools.call("duit_log_spend", {"place": "Jaya Grocer", "amount": 120, "bucket": "grocery", "paid_by": "hanz"},
                   msg("jaya grocer 120 shared hanz paid"))
    assert not r.get("error")


def test_first_share_copied_as_total_is_ignored(tools, ledger):
    text = "zapfan , lunch , RM13.20 hanz , 14.50 vanisa , Hanz paid"
    r = tools.call("duit_log_spend", {"place": "zapfan", "amount": "RM13.20", "paid_by": "hanz",
                                      "shares": {"hanz": "RM13.20", "vanisa": "14.50"}}, msg(text))
    assert not r.get("error")
    assert ledger.entry(1)["total_sen"] == 2770 and ledger.entry(1)["shares"] == {"hanz": 1320, "vanisa": 1450}
    # a total written on its own is still checked against the shares
    r = tools.call("duit_log_spend", {"place": "zapfan", "amount": "27.70", "shares": {"hanz": 13.2, "vanisa": 12}},
                   msg("zapfan 27.70 hanz 13.20 vanisa 12.00 hanz paid", msg_id="2"))
    assert "add up to" in r["error"]


def test_answer_cannot_overwrite_a_known_payer(tools, ledger):
    tools.call("duit_log_spend", {"place": "lunch", "amount": "56.50", "paid_by": "hanz"}, msg("lunch 56.50 hanz paid"))
    r = tools.call("duit_answer", {"entry_id": 1, "paid_by": "each"}, msg("#1 should be split", msg_id="2"))
    assert "duit_edit_spend" in r["error"] and ledger.entry(1)["paid_by"] == "hanz"


def test_plugin_starts_each_message_in_a_fresh_session(plugin):
    mod, hooks, tools_ = plugin
    calls = []

    class Gateway:
        _running_agents = {}

        def _session_key_for_source(self, source):
            return "tg:g"

        def _evict_cached_agent(self, key):
            calls.append(("evict", key))

        def _clear_conversation_scope(self, key, reason):
            calls.append(("clear", key))

    class Store:
        def reset_session(self, key):
            calls.append(("reset", key))

    class Event:
        message_id, text, raw_message, source = "77", "lunch 12", None, object()

    hooks["pre_gateway_dispatch"](event=Event(), gateway=Gateway(), session_store=Store())
    assert calls == [("evict", "tg:g"), ("clear", "tg:g"), ("reset", "tg:g")]
    calls.clear()
    Gateway._running_agents = {"tg:g": object()}          # a turn is still running: leave it alone
    hooks["pre_gateway_dispatch"](event=Event(), gateway=Gateway(), session_store=Store())
    assert calls == []

"""Installments: a fixed bill that only runs in some months, with a paid-so-far bar."""

import dataclasses

import pytest

from duit import db
from duit.config import Bucket
from duit.ledger import Ledger, LedgerError
from duit.replies import fixed_reply


@pytest.fixture
def led(cfg, clock):
    mop = Bucket("mop", "Mopping machine", "fixed", 25000, months=("2026-09", "2026-10", "2026-11"))
    c = dataclasses.replace(cfg, buckets={**cfg.buckets, "mop": mop})
    return Ledger(db.connect(":memory:"), c, clock)


def test_only_in_its_months(led):
    assert "mop" in led.status("2026-10")["people"]["hanz"]["buckets"]
    assert "mop" not in led.status("2026-12")["people"]["hanz"]["buckets"]
    assert {r["bucket"] for r in led.fixed_due("2026-12")} == {"house", "car"}
    with pytest.raises(LedgerError, match="only runs in"):
        led.pay_fixed("hanz", "mop", "2026-12")


def test_progress_bar_counts_all_months(led):
    led.pay_fixed("vanisa", "mop", "2026-09")
    r = led.pay_fixed("vanisa", "mop", "2026-10")
    assert fixed_reply(led.cfg, r) == ("✅ Mopping machine RM250.00 · Vanisa · Paid for October "
                                       "(2 of 3 paid, RM250.00 to go)")
    st = led.status("2026-10")
    v, h = st["people"]["vanisa"]["buckets"]["mop"], st["people"]["hanz"]["buckets"]["mop"]
    assert (v["status"], v["installment"]["done"], v["installment"]["spent"], v["installment"]["total"]) == \
        ("paid", 2, 50000, 75000)
    assert (h["status"], h["installment"]["done"], h["installment"]["left"]) == ("due", 0, 75000)
    c = st["combined"]["buckets"]["mop"]["installment"]
    assert (c["done"], c["count"], c["spent"], c["total"]) == (2, 6, 50000, 150000)
    assert ("2026-10", "hanz", "mop") in {(r["month"], r["person"], r["bucket"]) for r in led.fixed_due("2026-10")}


def test_new_bucket_gets_plan_rows_in_an_existing_month(cfg, clock):
    conn = db.connect(":memory:")
    Ledger(conn, cfg, clock).ensure_month("2026-10")   # month created before the installment existed
    mop = Bucket("mop", "Mopping machine", "fixed", 25000, months=("2026-10",))
    led = Ledger(conn, dataclasses.replace(cfg, buckets={**cfg.buckets, "mop": mop}), clock)
    assert led.status("2026-10")["people"]["hanz"]["buckets"]["mop"]["amount"] == 25000


def test_check_flags_bill_amount_that_differs_from_plan(led):
    from duit.integrity import check
    led.ensure_month("2026-10")
    led.conn.execute("UPDATE fixed_payments SET amount_sen=0 WHERE month='2026-10' AND bucket='mop' AND person='hanz'")
    assert check(led.conn, led.cfg) == ["2026-10 hanz mop: bill is 0 sen but the plan says 25000"]


# ---- bills and Chu Chu never land in weekday/weekend -------------------------------------------------
from duit.tools import Context, Tools  # noqa: E402


def _msg(text, msg_id, sender="hanz"):
    return Context(sender=sender, chat_id="g", msg_id=str(msg_id), text=text)


def test_bill_sent_as_spend_marks_it_paid_instead(led):
    t = Tools(led)
    text = "Hanz paid RM1000 house , RM300 car & RM250 mopping machine"
    r = t.call("duit_log_spend", {"place": "mopping machine", "amount": 250, "bucket": "daily", "paid_by": "hanz"},
               _msg(text, 32))
    assert r["reply"] == ("✅ Mopping machine RM250.00 · Hanz · Paid for October "
                          "(1 of 3 paid, RM500.00 to go)")
    assert led.conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 0
    r = t.call("duit_log_spend", {"place": "House", "amount": 1000}, _msg(text, 33))
    assert r["reply"].startswith("✅ House RM1,000.00 · Hanz · Paid for October")
    r = t.call("duit_log_spend", {"place": "rent", "amount": 1000}, _msg("rent 1000", 34))
    assert r["reply"] == "House is already marked paid for October."


def test_car_wash_is_not_the_car_bill(led):
    r = Tools(led).call("duit_log_spend", {"place": "car wash", "amount": 15, "bucket": "daily"}, _msg("car wash 15", 40))
    assert r["entry_id"] == 1 and led.entry(1)["bucket"] == "weekend"


def test_chuchu_overrules_a_daily_guess(led):
    t = Tools(led)
    t.call("duit_log_spend", {"place": "Watsons", "amount": 30, "bucket": "daily"}, _msg("watsons 30", 50))
    t.call("duit_log_spend", {"place": "Shampoo", "amount": 12, "bucket": "daily", "category": "Toiletries"},
           _msg("shampoo 12", 51))
    t.call("duit_log_spend", {"place": "Kopitiam", "amount": 9, "bucket": "daily", "category": "Food"},
           _msg("kopitiam 9", 52))
    assert [led.entry(i)["bucket"] for i in (1, 2, 3)] == ["chuchu", "chuchu", "weekend"]

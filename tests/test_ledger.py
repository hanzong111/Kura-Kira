import pytest

from duit.ledger import LedgerError


def test_simple_spend_sender_spent_and_paid(ledger):
    e = ledger.log_spend(sender="hanz", place="Sushi-Mentai", item="lunch", total="RM56.50",
                         bucket="daily", category="food")
    assert e["bucket"] == "weekend"              # Saturday
    assert e["category"] == "Food"
    assert e["shares"] == {"hanz": 5650}
    assert e["paid_by"] == "hanz"
    assert e["needs"] == []
    assert e["status"]["hanz"]["week"]["spent"] == 5650


def test_split_with_payer_tracks_shares_and_balance(ledger, clock):
    clock.set("2026-10-14T13:00")  # Wednesday
    e = ledger.log_spend(sender="hanz", place="Zapfan", item="lunch",
                         shares={"hanz": "RM13.20", "vanisa": "14.50"}, paid_by="Hanz", bucket="daily")
    assert e["total_sen"] == 2770 and e["bucket"] == "weekday"
    assert e["shares"] == {"hanz": 1320, "vanisa": 1450}
    assert ledger.balance()["owes"] == {"from": "vanisa", "to": "hanz", "amount": 1450}
    st = ledger.status()
    assert st["people"]["hanz"]["buckets"]["weekday"]["spent"] == 1320
    assert st["people"]["vanisa"]["buckets"]["weekday"]["spent"] == 1450
    assert st["paid"]["people"]["hanz"]["spends"] == 2770
    assert st["paid"]["people"]["vanisa"]["spends"] == 0


def test_split_without_payer_is_pending_until_answered(ledger):
    e = ledger.log_spend(sender="vanisa", place="Zapfan", shares={"hanz": 13.20, "vanisa": 14.50}, bucket="daily")
    assert e["paid_by"] is None and e["needs"] == ["payer"]
    # shares already count in budgets; payer shows as unknown
    st = ledger.status()
    assert st["people"]["hanz"]["buckets"]["weekend"]["spent"] == 1320
    assert st["paid"]["unknown"] == 2770
    assert [p["id"] for p in ledger.pending()] == [e["id"]]
    ledger.set_question(e["id"], "q-99")
    assert ledger.find_by_message("q-99")["id"] == e["id"]
    r = ledger.resolve(e["id"], paid_by="vanisa")
    assert r["needs"] == [] and ledger.pending() == []
    assert ledger.balance()["owes"] == {"from": "hanz", "to": "vanisa", "amount": 1320}


def test_someone_else_named_means_ask_payer(ledger):
    e = ledger.log_spend(sender="hanz", place="Grab", shares={"vanisa": 25}, bucket="daily")
    assert e["needs"] == ["payer"]


def test_each_paid_own_has_no_balance(ledger):
    ledger.log_spend(sender="hanz", place="Mamak", shares={"hanz": 10, "vanisa": 12}, paid_by="each",
                     bucket="daily")
    assert ledger.balance()["owes"] is None
    paid = ledger.status()["paid"]["people"]
    assert paid["hanz"]["spends"] == 1000 and paid["vanisa"]["spends"] == 1200


def test_shares_must_add_up_to_total(ledger):
    with pytest.raises(LedgerError, match="add up to 25.20 but the total is 27.70"):
        ledger.log_spend(sender="hanz", place="Zapfan", total=27.70, shares={"hanz": 13.20, "vanisa": 12.00})


def test_missing_amount_is_an_error_to_ask_about(ledger):
    with pytest.raises(LedgerError, match="amount is missing"):
        ledger.log_spend(sender="hanz", place="sushi mentai")


def test_unknown_bucket_goes_unsorted_then_learns(ledger):
    e = ledger.log_spend(sender="vanisa", place="Decathlon", total=120, bucket_options=["daily", "extra"])
    assert e["bucket"] is None and e["needs"] == ["bucket"]
    assert ledger.status()["people"]["vanisa"]["unsorted"] == 12000
    ledger.resolve(e["id"], bucket="daily", category="Sport")
    assert ledger.status()["people"]["vanisa"]["unsorted"] == 0
    # next time: learned, with a slightly different spelling
    e2 = ledger.log_spend(sender="hanz", place="decathlon", total=30)
    assert e2["bucket"] == "weekend" and e2["category"] == "Sport"


def test_learned_place_fuzzy_spelling(ledger):
    ledger.log_spend(sender="hanz", place="Sushi-Mentai", total=56.5, bucket="daily", category="Food")
    e = ledger.log_spend(sender="vanisa", place="sushimentai", total=26.2)
    assert (e["bucket"], e["category"]) == ("weekend", "Food")
    e = ledger.log_spend(sender="vanisa", place="sushi mentaii", total=20)
    assert e["category"] == "Food"


def test_learned_daily_place_follows_the_date(ledger, clock):
    ledger.log_spend(sender="hanz", place="Zapfan", total=10, bucket="weekend")  # explicit, on Saturday
    clock.set("2026-10-20T12:00")  # Tuesday
    assert ledger.log_spend(sender="hanz", place="zapfan", total=10)["bucket"] == "weekday"


def test_duplicate_message_is_logged_once(ledger):
    a = ledger.log_spend(sender="hanz", place="Lunch", total=12, bucket="daily", chat_id="g", msg_id="1")
    b = ledger.log_spend(sender="hanz", place="Lunch", total=12, bucket="daily", chat_id="g", msg_id="1")
    assert b["duplicate"] and b["id"] == a["id"]
    assert len(ledger.list_entries()) == 1


def test_fixed_bills_cannot_be_logged_as_spends(ledger):
    with pytest.raises(LedgerError, match="fixed bill"):
        ledger.log_spend(sender="hanz", place="rent", total=1000, bucket="house")


def test_unknown_person_rejected(ledger):
    with pytest.raises(LedgerError, match="unknown person"):
        ledger.log_spend(sender="bob", place="x", total=1)


def test_yesterday_uses_the_real_date(ledger, clock):
    clock.set("2026-10-19T09:00")  # Monday
    e = ledger.log_spend(sender="hanz", place="Dinner", total=40, bucket="daily", spent_on="yesterday")
    assert e["spent_on"] == "2026-10-18" and e["bucket"] == "weekend"


def test_edit_date_repicks_weekday_weekend(ledger):
    e = ledger.log_spend(sender="hanz", place="Dinner", total=40, bucket="daily")
    assert ledger.edit(e["id"], spent_on="2026-10-16")["bucket"] == "weekday"


def test_edit_total_and_split(ledger):
    e = ledger.log_spend(sender="hanz", place="Dinner", total=40, bucket="daily")
    assert ledger.edit(e["id"], total=45)["total_sen"] == 4500
    with pytest.raises(LedgerError, match="split"):
        s = ledger.log_spend(sender="hanz", place="Zapfan", shares={"hanz": 5, "vanisa": 5}, paid_by="hanz",
                             bucket="daily")
        ledger.edit(s["id"], total=12)


def test_undo_and_delete(ledger):
    ledger.log_spend(sender="hanz", place="A", total=10, bucket="daily")
    ledger.log_spend(sender="vanisa", place="B", total=20, bucket="daily")
    ledger.log_spend(sender="hanz", place="C", total=30, bucket="daily")
    assert ledger.undo("hanz")["place"] == "C"
    assert ledger.status()["people"]["hanz"]["buckets"]["weekend"]["spent"] == 1000
    with pytest.raises(LedgerError, match="already deleted"):
        ledger.delete(3)


def test_settle_up(ledger):
    ledger.log_spend(sender="hanz", place="Zapfan", shares={"hanz": 13.20, "vanisa": 14.50}, paid_by="hanz",
                     bucket="daily")
    r = ledger.settle(from_person="vanisa", to_person="hanz", amount=5)
    assert r["balance"]["owes"]["amount"] == 950
    r = ledger.settle(from_person="vanisa", to_person="hanz")  # the rest
    assert r["amount"] == 950 and r["balance"]["owes"] is None
    # settle-ups never touch budgets
    assert ledger.status()["people"]["vanisa"]["buckets"]["weekend"]["spent"] == 1450
    with pytest.raises(LedgerError, match="doesn't owe"):
        ledger.settle(from_person="vanisa", to_person="hanz")


def test_fixed_bills_vanisa_auto_paid_hanz_due(ledger):
    st = ledger.status()
    v, h = st["people"]["vanisa"]["buckets"], st["people"]["hanz"]["buckets"]
    assert v["house"]["status"] == v["car"]["status"] == "paid"
    assert h["house"]["status"] == h["car"]["status"] == "due"
    assert {(r["person"], r["bucket"]) for r in ledger.fixed_due()} == {("hanz", "house"), ("hanz", "car")}
    r = ledger.pay_fixed("Hanz", "house")
    assert r["already_paid"] is False and r["amount"] == 100000
    assert ledger.pay_fixed("hanz", "House")["already_paid"] is True
    st = ledger.status()
    assert st["people"]["hanz"]["buckets"]["house"]["status"] == "paid"
    assert st["combined"]["fixed"] == {"paid": 3, "count": 4}
    assert st["paid"]["people"]["hanz"]["fixed"] == 100000
    assert st["paid"]["people"]["vanisa"]["fixed"] == 130000


def test_new_month_resets_hanz_to_due(ledger, clock):
    ledger.pay_fixed("hanz", "house")
    clock.set("2026-11-01T08:00")
    st = ledger.status()
    assert st["people"]["hanz"]["buckets"]["house"]["status"] == "due"
    assert st["people"]["vanisa"]["buckets"]["house"]["status"] == "paid"


def test_plan_totals_match_the_agreed_plan(ledger):
    # October 2026: weekday targets 40 + 4x100 = 440, weekend 4x200 + 100 (lone Sat 31st) = 900
    st = ledger.status()
    for p in ("hanz", "vanisa"):
        b = st["people"][p]["buckets"]
        assert (b["weekday"]["target"], b["weekday"]["cap"]) == (10000, 44000)
        assert (b["weekend"]["target"], b["weekend"]["cap"]) == (20000, 90000)
        assert st["people"][p]["goals"]["cap"] == 44000 + 90000 + 30000 + 20000 + 6000 + 20000 + 5000 + 50000
        assert st["people"][p]["fixed"]["total"] == 130000
    assert st["combined"]["goals"]["cap"] == 2 * 265000
    assert st["combined"]["outflow_plan"] == 2 * (265000 + 130000)


def test_plan_change_copies_forward(ledger, clock):
    ledger.set_plan("grocery", 250)
    ledger.set_plan("petrol", 0, person="vanisa")
    clock.set("2026-11-03T08:00")
    b = ledger.status()["people"]
    assert b["hanz"]["buckets"]["grocery"]["cap"] == 25000
    assert b["vanisa"]["buckets"]["petrol"]["cap"] == 0
    assert b["vanisa"]["buckets"]["toll"]["cap"] == 5000


def test_alerts_at_80_and_over(ledger):
    a = ledger.log_spend(sender="vanisa", place="Petronas", total=150, bucket="petrol")
    assert a["alerts"] == []
    b = ledger.log_spend(sender="vanisa", place="Petronas", total=20, bucket="petrol")
    assert [(x["threshold"], x["left"]) for x in b["alerts"]] == [(0.8, 3000)]
    c = ledger.log_spend(sender="vanisa", place="Shell", total=40, bucket="petrol")
    assert [(x["threshold"], x["left"]) for x in c["alerts"]] == [(1.0, -1000)]
    assert ledger.status()["people"]["vanisa"]["buckets"]["petrol"]["status"] == "over"


def test_weekly_alert_uses_this_weeks_allowance(ledger):
    # Sat 17 Oct, nothing spent on the two earlier weekends -> 200 target + 400 saved = 600
    wk = ledger.status()["people"]["hanz"]["buckets"]["weekend"]["week"]
    assert (wk["target"], wk["carry"], wk["allowance"]) == (20000, 40000, 60000)
    e = ledger.log_spend(sender="hanz", place="Dinner", total=wk["allowance"] / 100 + 1, bucket="daily")
    assert e["alerts"][0]["scope"] == "week" and e["alerts"][0]["threshold"] == 1.0


def test_week_allowance_carries_forward(ledger, clock):
    def week(person="hanz"):
        return ledger.status()["people"][person]["buckets"]["weekend"]["week"]

    clock.set("2026-10-03T12:00")          # first weekend of October
    assert (week()["target"], week()["carry"], week()["allowance"]) == (20000, 0, 20000)
    ledger.log_spend(sender="hanz", place="Big dinner", total=300, bucket="weekend")   # over by 100
    clock.set("2026-10-10T12:00")
    assert (week()["carry"], week()["allowance"]) == (-10000, 10000)                  # pays it back
    assert (week("vanisa")["carry"], week("vanisa")["allowance"]) == (20000, 40000)   # saved 200
    ledger.log_spend(sender="hanz", place="Concert", total=500, bucket="weekend")     # way over
    clock.set("2026-10-17T12:00")
    assert week()["carry"] == -10000 + 20000 - 50000 and week()["allowance"] == 0     # never below 0
    clock.set("2026-11-07T12:00")
    # resets monthly: October's -400 is gone; only Sun 1 Nov (half a weekend, unspent) carries in
    assert (week()["carry"], week()["allowance"]) == (10000, 30000)


def test_tracking_start(cfg, clock):
    from dataclasses import replace
    from datetime import date

    from duit import db
    from duit.ledger import Ledger
    led = Ledger(db.connect(":memory:"), replace(cfg, tracking_start=date(2026, 10, 18)), clock)
    clock.set("2026-10-18T12:00")          # Sunday, first tracked day
    b = led.status()["people"]["hanz"]["buckets"]
    assert (b["weekend"]["week"]["target"], b["weekend"]["week"]["carry"]) == (10000, 0)   # half a weekend
    assert b["weekend"]["cap"] == 10000 + 20000 + 10000
    assert "week" not in b["weekday"]       # no weekdays left in this Mon-Sun week
    clock.set("2026-10-19T12:00")
    assert led.status()["people"]["hanz"]["buckets"]["weekday"]["week"]["allowance"] == 10000


def test_ask_extra_for_big_daily_spends(ledger):
    assert ledger.log_spend(sender="hanz", place="Shoes", total=250, bucket="daily")["ask_extra"] is True
    assert ledger.log_spend(sender="hanz", place="Lunch", total=20, bucket="daily")["ask_extra"] is False
    assert ledger.log_spend(sender="hanz", place="Shoes", total=250, bucket="extra")["ask_extra"] is False


def test_combined_is_sum_of_people(ledger):
    ledger.log_spend(sender="hanz", place="A", total=10, bucket="daily")
    ledger.log_spend(sender="vanisa", place="B", total=25, bucket="grocery")
    st = ledger.status()
    for k, b in st["combined"]["buckets"].items():
        if b["kind"] != "fixed":
            assert b["spent"] == sum(st["people"][p]["buckets"][k]["spent"] for p in st["people"])
    assert st["combined"]["goals"]["spent"] == 3500


def test_list_entries_filters(ledger):
    ledger.log_spend(sender="hanz", place="Sushi-Mentai", total=56.5, bucket="daily", category="Food")
    ledger.log_spend(sender="vanisa", place="Jaya Grocer", total=86, bucket="grocery", category="Groceries")
    ledger.log_spend(sender="hanz", place="Zapfan", shares={"hanz": 13.2, "vanisa": 14.5}, paid_by="hanz",
                     bucket="daily", category="Food")
    assert len(ledger.list_entries(person="vanisa")) == 2
    assert [e["place"] for e in ledger.list_entries(category="food")] == ["Zapfan", "Sushi-Mentai"]
    assert len(ledger.list_entries(bucket="grocery")) == 1
    assert len(ledger.list_entries(query="sushi")) == 1
    assert len(ledger.list_entries(paid_by="vanisa")) == 1


def test_balance_over_a_mixed_month(ledger, clock):
    ledger.log_spend(sender="hanz", place="Zapfan", shares={"hanz": 13.2, "vanisa": 14.5}, paid_by="hanz",
                     bucket="daily")                                         # V owes 14.50
    ledger.log_spend(sender="vanisa", place="Jaya Grocer", total=120, shares={"hanz": 60, "vanisa": 60},
                     paid_by="vanisa", bucket="grocery")                     # H owes 60
    ledger.log_spend(sender="hanz", place="Grab", shares={"vanisa": 25}, paid_by="hanz", bucket="daily")  # V owes 25
    ledger.log_spend(sender="vanisa", place="Lunch", total=15, bucket="daily")  # own, no effect
    # net: Hanz owed 14.50 + 25 - 60 = -20.50 -> Hanz owes Vanisa 20.50
    b = ledger.balance()
    assert b["owes"] == {"from": "hanz", "to": "vanisa", "amount": 2050}
    assert sum(b["net"].values()) == 0


def test_several_spends_in_one_message(ledger):
    a = ledger.log_spend(sender="hanz", place="Lunch", total=12, bucket="daily", chat_id="g", msg_id="7")
    b = ledger.log_spend(sender="hanz", place="Petrol", total=50, bucket="petrol", chat_id="g", msg_id="7:2")
    assert a["id"] != b["id"] and not b["duplicate"]
    assert ledger.find_by_message("7")["id"] in (a["id"], b["id"])


def test_before_start_maxed(cfg, clock):
    """Days before tracking began count as exactly on budget: full targets, no carry-over from them."""
    from dataclasses import replace
    from datetime import date

    from duit import db
    from duit.ledger import Ledger
    led = Ledger(db.connect(":memory:"), replace(cfg, tracking_start=date(2026, 10, 17), before_start="maxed"), clock)
    led.log_spend(sender="hanz", place="Old lunch", total=50, bucket="weekday", spent_on="2026-10-15")  # pre-start: ignored
    led.log_spend(sender="hanz", place="Cafe", total=44, bucket="daily")                                # Sat 17th
    b = led.status()["people"]["hanz"]["buckets"]
    assert (b["weekday"]["cap"], b["weekday"]["spent"], b["weekday"]["assumed"]) == (44000, 24000, 24000)
    assert (b["weekend"]["cap"], b["weekend"]["spent"], b["weekend"]["assumed"]) == (90000, 40000 + 4400, 40000)
    wk = b["weekend"]["week"]
    assert (wk["target"], wk["carry"], wk["allowance"], wk["spent"]) == (20000, 0, 20000, 4400)
    clock.set("2026-10-19T12:00")   # first tracked weekday week: clean RM100
    wd = led.status()["people"]["hanz"]["buckets"]["weekday"]["week"]
    assert (wd["target"], wd["carry"], wd["allowance"], wd["assumed"]) == (10000, 0, 10000, 0)


def test_before_start_maxed_mid_week(cfg, clock):
    """Start on a Wednesday: Mon-Tue of that week are assumed spent (2/5 of RM100), the rest is live."""
    from dataclasses import replace
    from datetime import date

    from duit import db
    from duit.ledger import Ledger
    clock.set("2026-10-21T12:00")
    led = Ledger(db.connect(":memory:"), replace(cfg, tracking_start=date(2026, 10, 21), before_start="maxed"), clock)
    led.log_spend(sender="hanz", place="Lunch", total=15, bucket="daily")
    wk = led.status()["people"]["hanz"]["buckets"]["weekday"]["week"]
    assert (wk["assumed"], wk["spent"], wk["allowance"], wk["left"]) == (4000, 5500, 10000, 4500)


def test_backfill_before_tracking(ledger):
    from datetime import date

    from duit.backfill import backfill
    rows = backfill(ledger, date(2026, 10, 1), date(2026, 10, 16))
    # per person: weekday Oct 1-2 (40), 5-9 (100), 12-16 (100); weekend Oct 3-4 (200), 10-11 (200)
    hanz = sorted((r["bucket"], r["from"], r["amount"]) for r in rows if r["person"] == "hanz")
    assert hanz == [("weekday", "2026-10-01", 4000), ("weekday", "2026-10-05", 10000), ("weekday", "2026-10-12", 10000),
                    ("weekend", "2026-10-03", 20000), ("weekend", "2026-10-10", 20000)]
    b = ledger.status()["people"]["hanz"]["buckets"]
    assert (b["weekday"]["spent"], b["weekend"]["spent"]) == (24000, 40000)
    assert b["weekend"]["week"]["carry"] == 0           # on budget -> nothing saved, nothing owed
    assert all(r["duplicate"] for r in backfill(ledger, date(2026, 10, 1), date(2026, 10, 16)))  # re-run safe

"""The 'how are we doing?' summary: layout only, every number from the ledger."""

from duit.replies import status_text


def test_summary_layout(ledger):
    ledger.log_spend(sender="hanz", place="Jaya Grocer", total=100, bucket="grocery")      # shared: RM50 each
    ledger.log_spend(sender="vanisa", place="Concert", total=320, bucket="extra")          # only Vanisa's: over
    ledger.log_spend(sender="hanz", place="Dinner", total=30, bucket="daily")              # Sat 17 Oct
    text = status_text(ledger.cfg, ledger.status())
    lines = text.splitlines()
    assert lines[0] == "📊 **DUIT · October 2026**"
    assert lines[1].startswith("Month elapsed: 55% · Budget used: ")
    assert "👤 **Hanz · " in text and "👤 **Vanisa · " in text
    # Sat 17 Oct: target RM200 + RM400 saved on the two earlier weekends -> RM600, minus RM30
    assert "• Weekend: **RM570.00 left**\n  Includes RM400.00 carried forward" in text
    assert "• Grocery: RM150.00 left" in text                                             # same for both: one line
    assert "✨ **Extra remaining**\nHanz: RM300.00 · Vanisa: over by RM20.00 🟥" in text   # differs: per person
    assert "⏳ **Fixed bills due**\n• Hanz: Parents RM500.00, House RM1,000.00, Car RM300.00\n• Vanisa: Parents RM500.00" in text
    assert text.endswith("💸 **Settlement**\nVanisa owes Hanz **RM50.00**")


def test_summary_for_one_person_and_all_paid(ledger):
    for p, bills in (("hanz", ["parents", "house", "car"]), ("vanisa", ["parents"])):
        for b in bills:
            ledger.pay_fixed(p, b)
    text = status_text(ledger.cfg, ledger.status(), "vanisa")
    assert "Hanz" not in text.split("💸")[0]
    assert "🛒 **Other monthly balances**\n" in text and "✅ **All fixed bills paid**" in text
    assert text.endswith("All settled ✓")

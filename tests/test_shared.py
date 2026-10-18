"""Shared buckets (grocery, Chu Chu / Toiletries, petrol, toll): borne half each, whoever paid."""

import sqlite3

from duit import db
from duit.integrity import check


def test_plain_shared_spend_is_split_and_payer_kept(ledger):
    e = ledger.log_spend(sender="hanz", place="Jaya Grocer", total=100, bucket="grocery")
    assert e["shares"] == {"hanz": 5000, "vanisa": 5000} and e["paid_by"] == "hanz"
    assert ledger.balance()["owes"]["from"] == "vanisa" and ledger.balance()["owes"]["amount"] == 5000
    st = ledger.status()
    assert st["people"]["hanz"]["buckets"]["grocery"]["spent"] == 5000
    assert st["people"]["vanisa"]["buckets"]["grocery"]["spent"] == 5000
    assert st["paid"]["people"]["hanz"]["spends"] == 10000 and st["paid"]["people"]["vanisa"]["spends"] == 0


def test_odd_sen_split_exactly(ledger):
    e = ledger.log_spend(sender="vanisa", place="Watsons", total="74.01", bucket="chuchu")
    assert sum(e["shares"].values()) == 7401 and sorted(e["shares"].values()) == [3700, 3701]


def test_stated_owner_wins_over_shared_rule(ledger):
    e = ledger.log_spend(sender="hanz", place="Guardian", total=30, bucket="chuchu",
                         shares={"vanisa": 30}, paid_by="hanz", shares_given=True)
    assert e["shares"] == {"vanisa": 3000}


def test_daily_spend_still_belongs_to_payer(ledger):
    e = ledger.log_spend(sender="hanz", place="Sushi Zanmai", total=70, bucket="daily", paid_by="vanisa",
                         shares={"vanisa": 70}, shares_given=False)
    assert e["shares"] == {"vanisa": 7000}


def test_answering_into_shared_bucket_splits_and_back_again(ledger):
    e = ledger.log_spend(sender="vanisa", place="Mystery shop", total=40, bucket_options=["chuchu", "extra"],
                         shares={"vanisa": 40}, shares_given=False)
    assert e["shares"] == {"vanisa": 4000} and e["needs"] == ["bucket"]
    r = ledger.resolve(e["id"], bucket="chuchu")
    assert r["shares"] == {"hanz": 2000, "vanisa": 2000}
    assert set(r["status"]) == {"hanz", "vanisa"}
    back = ledger.edit(e["id"], bucket="extra")
    assert back["shares"] == {"vanisa": 4000}


def test_edit_total_of_shared_spend_resplits(ledger):
    e = ledger.log_spend(sender="hanz", place="Petronas", total=80, bucket="petrol")
    r = ledger.edit(e["id"], total=90)
    assert r["shares"] == {"hanz": 4500, "vanisa": 4500}


def test_reshare_and_integrity(ledger):
    e = ledger.log_spend(sender="hanz", place="Touch n Go", total=50, bucket="toll")
    ledger.conn.execute("DELETE FROM shares WHERE entry_id=?", (e["id"],))       # an entry from before the rule
    ledger.conn.execute("INSERT INTO shares VALUES (?, 'hanz', 5000)", (e["id"],))
    assert any("isn't split evenly" in p for p in check(ledger.conn, ledger.cfg))
    changed = ledger.reshare()
    assert [(c["id"], c["after"]) for c in changed] == [(e["id"], {"hanz": 2500, "vanisa": 2500})]
    assert check(ledger.conn, ledger.cfg) == [] and ledger.reshare() == []


def test_migration_marks_old_splits_as_said(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(db.SCHEMA.replace(
        "    shares_given    INTEGER NOT NULL DEFAULT 0, -- 1 = the message said whose it is; 0 = by rule (payer / shared bucket)\n", ""))
    old.execute("INSERT INTO meta VALUES ('schema_version', '1')")
    for i, shares in ((1, [("hanz", 100)]), (2, [("hanz", 50), ("vanisa", 50)])):
        old.execute("INSERT INTO entries(id, created_at, spent_on, place, total_sen, sender) "
                    "VALUES (?, 'x', '2026-10-01', 'p', ?, 'hanz')", (i, sum(a for _, a in shares)))
        old.executemany("INSERT INTO shares VALUES (?,?,?)", [(i, p, a) for p, a in shares])
    old.commit()
    old.close()
    conn = db.connect(path)
    assert [tuple(r) for r in conn.execute("SELECT id, shares_given FROM entries ORDER BY id")] == [(1, 0), (2, 1)]
    assert conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == "2"


def test_advance_shows_as_transfer_and_moves_balance_only(ledger):
    ledger.settle(from_person="hanz", to_person="vanisa", amount=400, on="2026-10-01", raw_text="upfront")
    ledger.log_spend(sender="vanisa", place="Lotus's", total=100, bucket="grocery")
    st = ledger.status()
    assert st["paid"]["transfers"] == [{"on": "2026-10-01", "from": "hanz", "to": "vanisa", "amount": 40000,
                                        "note": "upfront"}]
    assert st["balance"]["owes"] == {"from": "vanisa", "to": "hanz", "amount": 35000}   # 400 - half of 100
    assert st["people"]["hanz"]["buckets"]["grocery"]["spent"] == 5000

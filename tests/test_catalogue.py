import pytest

from duit.catalogue import lookup
from duit.tools import Context, Tools


@pytest.mark.parametrize("place,bucket,category", [
    ("Sushi Zanmai", "daily", "Food"), ("sushimentai", "daily", "Food"), ("zapfan", "daily", "Food"),
    ("jaya grocer bangsar", "grocery", "Groceries"), ("99 speedmart", "grocery", "Groceries"),
    ("gsc movie", "daily", "Leisure"), ("red box", "daily", "Leisure"),
    ("golf kgsaa", "daily", "Sport"), ("tpc", "daily", "Sport"), ("badminton court", "daily", "Sport"),
    ("petronas", "petrol", "Transport"), ("tng reload for toll", "toll", "Transport"), ("grab", "daily", "Transport"),
    ("watsons", "chuchu", "Toiletries"), ("whiskas + litter", "chuchu", "Pet"), ("chu chu vet", "chuchu", "Pet"),
    ("parents", "parents", "Family"), ("mr diy", "daily", "Shopping"), ("grab food", "daily", "Food"),
    ("grabmart", "grocery", "Groceries"),
])
def test_known_merchants(place, bucket, category):
    m = lookup(place)
    assert m is not None and (m.bucket, m.category) == (bucket, category)


@pytest.mark.parametrize("place,expected", [
    ("shell out", "Shell Out"),          # longest phrase wins: the restaurant, not the petrol station
    ("five guys burger", "burger"),      # 'five' is whole-name-only: never petrol inside a longer name
    ("village park nasi lemak", "Village Park Restaurant"),
])
def test_ambiguous_names(place, expected):
    assert lookup(place).name == expected


@pytest.mark.parametrize("place", ["decathlon", "uniqlo", "new shoes", "pad thai", "mines"])
def test_unknown_stays_unknown(place):
    assert lookup(place) is None


def test_catalogue_fills_bucket_and_category(ledger):
    t = Tools(ledger)
    r = t.call("duit_log_spend", {"place": "Jaya Grocer", "amount": 86}, Context(sender="vanisa", msg_id="1"))
    e = ledger.entry(r["entry_id"])
    assert (e["bucket"], e["category"]) == ("grocery", "Groceries")


def test_catalogue_settles_an_unsure_model(ledger):
    t = Tools(ledger)
    r = t.call("duit_log_spend", {"place": "Petronas", "amount": 80, "bucket_options": ["petrol", "daily"]},
               Context(sender="hanz", msg_id="1"))
    assert r["needs"] == [] and ledger.entry(r["entry_id"])["bucket"] == "petrol"


def test_model_sure_bucket_wins(ledger):
    t = Tools(ledger)
    r = t.call("duit_log_spend", {"place": "Shell", "amount": 12, "bucket": "daily", "category": "Food"},
               Context(sender="hanz", msg_id="1"))                       # snacks at Shell, model said so
    assert ledger.entry(r["entry_id"])["bucket"] == "weekend"


def test_taught_place_beats_catalogue(ledger):
    t = Tools(ledger)
    ledger.learn_place("Watsons", bucket="extra", category="Shopping")     # the couple said: makeup = extra
    r = t.call("duit_log_spend", {"place": "watsons", "amount": 90}, Context(sender="vanisa", msg_id="1"))
    e = ledger.entry(r["entry_id"])
    assert (e["bucket"], e["category"]) == ("extra", "Shopping")

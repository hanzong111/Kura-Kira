from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from duit import config, db
from duit.ledger import Ledger

KL = ZoneInfo("Asia/Kuala_Lumpur")


class Clock:
    def __init__(self, iso: str):
        self.set(iso)

    def set(self, iso: str):
        self.now = datetime.fromisoformat(iso).replace(tzinfo=KL)

    def __call__(self):
        return self.now


@pytest.fixture
def cfg():
    return config.load(config.ROOT / "config.example.toml")


@pytest.fixture
def clock():
    return Clock("2026-10-17T13:00")  # Saturday


@pytest.fixture
def ledger(cfg, clock):
    return Ledger(db.connect(":memory:"), cfg, clock)

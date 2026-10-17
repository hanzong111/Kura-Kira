import json
import os
import sys

import anyio
import pytest
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp import ClientSession

from duit import server
from duit.config import ROOT


@pytest.fixture
def srv(cfg, ledger):
    return server.build(cfg, ledger)


def call(srv, tool, **args):
    async def go():
        async with Client(srv) as c:
            r = await c.call_tool(tool, args)
            assert not r.is_error, r
            return json.loads(r.content[0].text)  # Hermes sees this JSON text
    return anyio.run(go)


def test_tool_list_is_ledger_only(srv):
    assert set(server.tool_names(srv)) == {
        "log_spend", "answer", "record_question", "edit_spend", "delete_spend", "settle_up", "pay_fixed",
        "set_plan", "lookup_place", "status", "list_spends", "pending", "fixed_due"}


def test_log_spend_reply(srv):
    r = call(srv, "log_spend", sender="hanz", place="Sushi-Mentai", amount="RM56.50", bucket="daily",
             category="food", msg_id="1", chat_id="g")
    assert r["reply"].startswith("✅ #1 Sushi-Mentai · Weekend · RM56.50 · Hanz — RM")
    assert r["reply"].endswith("left this weekend 🟩")
    assert r["question"] is None


def test_split_without_payer_returns_question_then_answer(srv):
    r = call(srv, "log_spend", sender="vanisa", place="Zapfan", shares={"Hanz": 13.2, "Vanisa": "14.50"},
             bucket="daily")
    q = r["question"]
    assert q["asks"] == "payer" and q["options"] == ["Hanz", "Vanisa", "Each paid own"]
    assert q["text"] == "@Hanz @Vanisa Zapfan RM27.70 (Hanz RM13.20 · Vanisa RM14.50): who paid?"
    call(srv, "record_question", entry_id=r["entry_id"], question_msg_id="555")
    a = call(srv, "answer", reply_to_msg_id="555", paid_by="Hanz")
    assert a["needs"] == [] and "paid by Hanz" in a["reply"]
    assert "Vanisa owes Hanz RM14.50" in call(srv, "status")["reply"]


def test_errors_come_back_as_ask(srv):
    r = call(srv, "log_spend", sender="hanz", place="Zapfan", amount=27.7, shares={"hanz": 13.2, "vanisa": 12})
    assert r["ask"] is True and "add up to" in r["error"]


def test_stranger_telegram_id_rejected(srv):
    r = call(srv, "log_spend", sender="123456", place="x", amount=1)
    assert "not one of us" in r["error"]


def test_fixed_and_settle_replies(srv):
    assert call(srv, "pay_fixed", person_name="hanz", bill="house")["reply"].startswith("✅ House RM1,000.00 · Hanz")
    assert "already marked paid" in call(srv, "pay_fixed", person_name="Hanz", bill="House")["reply"]
    assert "Car RM300.00 is due" in call(srv, "fixed_due")["reply"]
    call(srv, "log_spend", sender="hanz", place="Grab", shares={"vanisa": 25}, paid_by="hanz", bucket="daily")
    r = call(srv, "settle_up", from_person="vanisa", to_person="hanz")
    assert "all settled" in r["reply"]


def test_unsorted_question_and_learned_place(srv):
    r = call(srv, "log_spend", sender="vanisa", place="Decathlon", amount=120, bucket_options=["daily", "extra"])
    assert r["question"]["options"] == ["Everyday (weekday/weekend)", "Extra", "Other…"]
    assert "❓ Unsorted" in r["reply"]
    call(srv, "answer", bucket="daily", category="Sport")  # only one pending -> no id needed
    assert call(srv, "lookup_place", name="decathlon")["place"]["category"] == "Sport"


def test_stdio_server_starts(tmp_path):
    """The real entry point Hermes will launch."""
    params = StdioServerParameters(command=sys.executable, args=["-m", "duit.server"], cwd=str(ROOT),
                                   env={**os.environ, "DUIT_DB": str(tmp_path / "t.db"),
                                        "DUIT_CONFIG": str(ROOT / "config.example.toml")})

    async def go():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                tools = await s.list_tools()
                r = await s.call_tool("status", {})
                return [t.name for t in tools.tools], r
    names, r = anyio.run(go)
    assert "log_spend" in names
    assert json.loads(r.content[0].text)["reply"].startswith("📊")


def test_reply_wording(srv):
    r = call(srv, "log_spend", sender="vanisa", place="Petronas", amount=170, bucket="petrol")
    assert r["reply"].splitlines()[0] == "✅ #1 Petronas · Petrol · RM170.00 · Vanisa — RM30.00 left in Petrol for October 🟨"
    assert r["reply"].splitlines()[1].startswith("⚠️ Vanisa · Petrol at 85% this month")
    r = call(srv, "log_spend", sender="vanisa", place="Decathlon", amount=120)
    assert r["reply"] == "✅ #2 Decathlon · ❓ Unsorted · RM120.00 · Vanisa"

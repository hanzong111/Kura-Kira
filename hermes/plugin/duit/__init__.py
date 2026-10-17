"""Hermes plugin: registers the duit ledger tools and the hooks that keep numbers out of the model's hands.

Install by symlinking this folder into the profile's plugins dir (see README).

- Tools read the sender's Telegram user ID, chat id and message id from the gateway's session context,
  so the model can't choose who a spend belongs to.
- `pre_gateway_dispatch` keeps the message exactly as sent (text + Telegram send time) before the model
  sees it; tools check every amount against that text and date spends by when they were sent.
  (`pre_llm_call` is the fallback for one-shot runs without a gateway.)
- `transform_llm_output` replaces the model's final text with the ledger's own reply lines for that
  message, so every number posted in the group comes from code. The model's words are only kept when
  no tool produced a reply (e.g. it asks "How much?"), or appended after a tool refused something.
Outside the gateway (eval / CLI) the same HERMES_SESSION_* names are read from the environment.
"""

import json
import os
import sys
import threading
from collections import OrderedDict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]  # <repo>/hermes/plugin/duit/__init__.py
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from duit import config, db  # noqa: E402
from duit.tools import Context, Tools, chat_lines, specs  # noqa: E402

_lock = threading.Lock()
_tools = None
_KEEP = 500
_messages: "OrderedDict[str, dict]" = OrderedDict()   # msg_id -> {"text", "sent_at"}
_turns: "OrderedDict[str, dict]" = OrderedDict()      # msg_id -> {"lines": [...], "refused": bool}


def _remember(store: OrderedDict, key: str, value) -> None:
    store[key] = value
    store.move_to_end(key)
    while len(store) > _KEEP:
        store.popitem(last=False)


def _get_tools() -> Tools:
    global _tools
    if _tools is None:
        from duit.ledger import Ledger
        _tools = Tools(Ledger(db.connect(), config.load()))
    return _tools


def _session(name: str) -> str:
    try:
        from gateway.session_context import get_session_env
        return get_session_env(name, "") or ""
    except Exception:  # running outside Hermes
        return os.environ.get(name, "")


def _context() -> Context:
    msg_id = _session("HERMES_SESSION_MESSAGE_ID")
    seen = _messages.get(msg_id, {})
    return Context(sender_telegram_id=_session("HERMES_SESSION_USER_ID"),
                   chat_id=_session("HERMES_SESSION_CHAT_ID"), msg_id=msg_id,
                   text=seen.get("text"), sent_at=seen.get("sent_at"))


def _handler(name):
    def handle(params, **kwargs):
        del kwargs
        ctx = _context()
        with _lock:  # one ledger write at a time
            result = _get_tools().call(name, params, ctx)
            turn = _turns.get(ctx.msg_id) or {"lines": [], "refused": False}
            if result.get("error"):
                turn["refused"] = True
            elif not (result.get("duplicate") and turn["lines"]):
                turn["lines"].extend(chat_lines(result))
            _remember(_turns, ctx.msg_id, turn)
        return json.dumps(result, ensure_ascii=False)
    return handle


def _on_dispatch(event=None, **_):
    """Keep the message as the user sent it, before anything else touches it."""
    try:
        msg_id = getattr(event, "message_id", None)
        if msg_id:
            raw = getattr(event, "raw_message", None)
            _remember(_messages, str(msg_id), {"text": getattr(event, "text", None),
                                               "sent_at": getattr(raw, "date", None)})
    except Exception:
        pass
    return None  # observe only


def _on_pre_llm(user_message=None, **_):
    msg_id = _session("HERMES_SESSION_MESSAGE_ID")
    if msg_id and msg_id not in _messages and isinstance(user_message, str):
        _remember(_messages, msg_id, {"text": user_message, "sent_at": None})
    return None


def _on_output(response_text=None, **_):
    turn = _turns.pop(_session("HERMES_SESSION_MESSAGE_ID"), None)
    if not turn or not turn["lines"]:
        return None  # nothing from the ledger: keep the model's words (a question, or NO_REPLY)
    lines = list(turn["lines"])
    said = (response_text or "").strip()
    if turn["refused"] and said not in ("", "NO_REPLY", "[SILENT]"):
        # a tool refused part of the message; keep only the model's new lines (its question about it)
        posted = {ln.strip() for ln in "\n".join(lines).splitlines()}
        lines += [ln for ln in said.splitlines() if ln.strip() and ln.strip() not in posted]
    return "\n".join(lines)


def register(ctx):
    cfg = config.load()
    for spec in specs(cfg):
        ctx.register_tool(name=spec["name"], toolset="duit", schema=spec, handler=_handler(spec["name"]))
    ctx.register_hook("pre_gateway_dispatch", _on_dispatch)
    ctx.register_hook("pre_llm_call", _on_pre_llm)
    ctx.register_hook("transform_llm_output", _on_output)

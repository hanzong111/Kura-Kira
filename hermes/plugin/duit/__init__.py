"""Hermes plugin: registers the duit ledger tools.

Install by symlinking this folder into the profile's plugins dir (see README). The sender's Telegram
user ID, chat id and message id are read from the gateway's session context, so the model can't
choose who a spend belongs to. Outside the gateway (eval / CLI) the same HERMES_SESSION_* names are
read from the environment.
"""

import json
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]  # <repo>/hermes/plugin/duit/__init__.py
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from duit import config, db  # noqa: E402
from duit.ledger import Ledger  # noqa: E402
from duit.tools import Context, Tools, specs  # noqa: E402

_lock = threading.Lock()
_tools = None


def _get_tools() -> Tools:
    global _tools
    if _tools is None:
        cfg = config.load()
        _tools = Tools(Ledger(db.connect(), cfg))
    return _tools


def _session(name: str) -> str:
    try:
        from gateway.session_context import get_session_env
        return get_session_env(name, "") or ""
    except Exception:  # running outside Hermes
        import os
        return os.environ.get(name, "")


def _context() -> Context:
    return Context(sender_telegram_id=_session("HERMES_SESSION_USER_ID"),
                   chat_id=_session("HERMES_SESSION_CHAT_ID"),
                   msg_id=_session("HERMES_SESSION_MESSAGE_ID"))


def _handler(name):
    def handle(params, **kwargs):
        del kwargs
        with _lock:  # one ledger write at a time
            result = _get_tools().call(name, params, _context())
        return json.dumps(result, ensure_ascii=False)
    return handle


def register(ctx):
    cfg = config.load()
    for spec in specs(cfg):
        ctx.register_tool(name=spec["name"], toolset="duit", schema=spec, handler=_handler(spec["name"]))

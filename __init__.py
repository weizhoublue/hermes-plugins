"""Project-local hook monitor plugin.

Registers every currently supported plugin hook and appends a JSONL record to
~/hermesmonitor/hook.log whenever a hook fires.

This plugin is intentionally observer-only: every callback returns None so it
never blocks tools, injects LLM context, rewrites outputs, or alters gateway
dispatch.
"""

from __future__ import annotations

import json
import threading
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from reprlib import repr as limited_repr
from typing import Any

from hermes_cli.plugins import VALID_HOOKS

LOG_PATH = Path("~/hermesmonitor/hook.log").expanduser()
_WRITE_LOCK = threading.Lock()
_MAX_SERIALIZE_DEPTH = 6
_HOOK_NAMES = (
    "pre_tool_call",
    "post_tool_call",
    "transform_terminal_output",
    "transform_tool_result",
    "pre_llm_call",
    "post_llm_call",
    "pre_api_request",
    "post_api_request",
    "on_session_start",
    "on_session_end",
    "on_session_finalize",
    "on_session_reset",
    "subagent_stop",
    "pre_gateway_dispatch",
)


def _type_name(value: Any) -> str:
    cls = type(value)
    return f"{cls.__module__}.{cls.__qualname__}"


def _fallback_repr(value: Any) -> str:
    try:
        return limited_repr(value)
    except Exception:
        return f"<unreprable {_type_name(value)}>"


def _serialize(value: Any, *, depth: int = 0, seen: set[int] | None = None) -> Any:
    if seen is None:
        seen = set()

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Path):
        return str(value)

    if depth >= _MAX_SERIALIZE_DEPTH:
        return {"__type__": _type_name(value), "__repr__": _fallback_repr(value)}

    obj_id = id(value)
    if obj_id in seen:
        return {"__type__": _type_name(value), "__repr__": "<cycle>"}

    if isinstance(value, dict):
        seen.add(obj_id)
        try:
            return {
                str(key): _serialize(item, depth=depth + 1, seen=seen)
                for key, item in value.items()
            }
        finally:
            seen.discard(obj_id)

    if isinstance(value, (list, tuple, set, frozenset)):
        seen.add(obj_id)
        try:
            return [_serialize(item, depth=depth + 1, seen=seen) for item in value]
        finally:
            seen.discard(obj_id)

    if is_dataclass(value) and not isinstance(value, type):
        seen.add(obj_id)
        try:
            payload = {"__type__": _type_name(value)}
            for field in fields(value):
                payload[field.name] = _serialize(
                    getattr(value, field.name),
                    depth=depth + 1,
                    seen=seen,
                )
            return payload
        finally:
            seen.discard(obj_id)

    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
        except Exception:
            return {"__type__": _type_name(value), "__repr__": _fallback_repr(value)}
        return {
            "__type__": _type_name(value),
            "data": _serialize(dumped, depth=depth + 1, seen=seen),
        }

    return {"__type__": _type_name(value), "__repr__": _fallback_repr(value)}


def _append_log_entry(hook_name: str, kwargs: dict[str, Any]) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hook": hook_name,
        "kwargs": _serialize(kwargs),
    }
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _make_hook_callback(hook_name: str):
    def _callback(**kwargs: Any) -> None:
        _append_log_entry(hook_name, kwargs)
        return None

    _callback.__name__ = f"hook_monitor_{hook_name}"
    return _callback


def register(ctx) -> None:
    """Register observer-only callbacks for every currently supported hook."""
    for hook_name in _HOOK_NAMES:
        if hook_name not in VALID_HOOKS:
            continue
        ctx.register_hook(hook_name, _make_hook_callback(hook_name))

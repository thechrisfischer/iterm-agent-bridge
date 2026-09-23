"""Validation for the privacy-limited local bridge protocol."""

import re
import uuid

PROTOCOL_VERSION = 1
AGENTS = frozenset(("claude", "codex", "cursor", "kimi", "agy"))
KINDS = frozenset((
    "turn_started", "tool_started", "tool_finished", "permission_requested",
    "permission_resolved", "child_started", "child_finished", "turn_finished",
    "interrupted", "session_closed",
))
NONCE_RE = re.compile(r"^[0-9a-f]{32}$")


class ProtocolError(ValueError):
    """A message is malformed or violates the published event contract."""


def _text(value, field, limit=256, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > limit:
        raise ProtocolError("invalid %s" % field)
    return value


def _base(message):
    if not isinstance(message, dict) or message.get("protocol_version") != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol version")
    agent = _text(message.get("agent"), "agent", 32)
    if agent not in AGENTS:
        raise ProtocolError("unsupported agent")
    session = _text(message.get("iterm_session_id"), "iterm_session_id")
    nonce = _text(message.get("launch_nonce"), "launch_nonce", 32)
    if not NONCE_RE.match(nonce):
        raise ProtocolError("invalid launch_nonce")
    return agent, session, nonce


def validate_register(message):
    agent, session, nonce = _base(message)
    basename = _text(message.get("project_basename"), "project_basename", 255)
    if message.get("type") != "register":
        raise ProtocolError("expected register")
    return {"agent": agent, "iterm_session_id": session, "launch_nonce": nonce,
            "project_basename": basename}


def validate_event(message):
    agent, session, nonce = _base(message)
    if message.get("type") != "event":
        raise ProtocolError("expected event")
    kind = _text(message.get("kind"), "kind", 64)
    if kind not in KINDS:
        raise ProtocolError("unsupported event kind")
    event_id = _text(message.get("event_id"), "event_id", 36)
    try:
        uuid.UUID(event_id)
    except (ValueError, AttributeError):
        raise ProtocolError("invalid event_id")
    sequence = message.get("sequence")
    if not isinstance(sequence, int) or sequence < 0:
        raise ProtocolError("invalid sequence")
    child_id = _text(message.get("child_id"), "child_id", required=False)
    if kind in ("child_started", "child_finished") and child_id is None:
        raise ProtocolError("child lifecycle requires child_id")
    return {"agent": agent, "iterm_session_id": session, "launch_nonce": nonce,
            "kind": kind, "event_id": event_id, "sequence": sequence,
            "turn_id": _text(message.get("turn_id"), "turn_id", required=False),
            "child_id": child_id,
            "reason": _text(message.get("reason"), "reason", required=False)}

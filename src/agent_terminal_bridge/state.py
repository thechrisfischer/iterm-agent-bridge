"""Deterministic state machine; it never stores agent content."""

from dataclasses import dataclass, field
from time import time


@dataclass
class SessionState:
    agent: str
    session_id: str
    nonce: str
    project_basename: str
    delivery: str = "unavailable"
    turn_active: bool = False
    permission_pending: bool = False
    children: set = field(default_factory=set)
    last_sequence: int = -1
    event_ids: set = field(default_factory=set)
    updated_at: float = field(default_factory=time)
    closed_at: float = None

    @property
    def display_state(self):
        if self.permission_pending:
            return "waiting"
        if self.turn_active or self.children:
            return "working"
        return "idle"

    def apply(self, event):
        if event["event_id"] in self.event_ids or event["sequence"] <= self.last_sequence:
            return False
        self.event_ids.add(event["event_id"])
        self.last_sequence = event["sequence"]
        kind = event["kind"]
        if kind in ("turn_started", "tool_started"):
            self.turn_active = True
        elif kind == "permission_requested":
            self.permission_pending = True
        elif kind == "permission_resolved":
            self.permission_pending = False
        elif kind == "child_started":
            self.children.add(event["child_id"])
        elif kind == "child_finished":
            self.children.discard(event["child_id"])
        elif kind in ("turn_finished", "interrupted"):
            self.turn_active = False
            self.permission_pending = False
        elif kind == "session_closed":
            self.turn_active = False
            self.permission_pending = False
            self.children.clear()
            self.closed_at = time()
        self.updated_at = time()
        return True

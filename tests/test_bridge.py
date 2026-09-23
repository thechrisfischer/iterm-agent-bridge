import unittest

from agent_terminal_bridge.protocol import ProtocolError, validate_event, validate_register
from agent_terminal_bridge.server import Bridge
from agent_terminal_bridge.publisher import session_uuid, publish
from agent_terminal_bridge.cli import socket_ready


def registration(nonce="a" * 32):
    return {"type":"register","protocol_version":1,"agent":"codex","iterm_session_id":"s","launch_nonce":nonce,"project_basename":"bridge"}


def event(kind, sequence, **extra):
    body=dict(registration(),type="event",event_id="123e4567-e89b-42d3-a456-%012d"%sequence,sequence=sequence,kind=kind)
    body.update(extra); return body


class BridgeTests(unittest.TestCase):
    def test_child_requires_identity(self):
        with self.assertRaises(ProtocolError): validate_event(event("child_started", 0))

    def test_permission_precedes_child_work(self):
        bridge=Bridge(); bridge.handle(registration())
        bridge.handle(event("child_started",0,child_id="c"))
        self.assertEqual(bridge.handle(event("permission_requested",1))["state"],"waiting")
        self.assertEqual(bridge.handle(event("permission_resolved",2))["state"],"working")
        self.assertEqual(bridge.handle(event("child_finished",3,child_id="c"))["state"],"idle")

    def test_stale_nonce_is_rejected(self):
        bridge=Bridge(); bridge.handle(registration("a"*32)); bridge.handle(registration("b"*32))
        with self.assertRaises(ProtocolError): bridge.handle(event("turn_started",0))

    def test_publishes_transition_to_explicit_iterm_session(self):
        published=[]
        bridge=Bridge(publisher=lambda session, state: published.append((session, state.display_state)) or True)
        self.assertEqual(bridge.handle(registration())["delivery"], "ready")
        bridge.handle(event("turn_started",0))
        self.assertEqual(published, [("s", "idle"), ("s", "working")])

    def test_turn_end_clears_permission(self):
        bridge=Bridge(publisher=lambda session, state: True); bridge.handle(registration())
        bridge.handle(event("permission_requested",0))
        self.assertEqual(bridge.handle(event("turn_finished",1))["state"], "idle")

    def test_iterm_identifier_requires_uuid(self):
        self.assertEqual(session_uuid("w0t0p0:123e4567-e89b-42d3-a456-426614174000"), "123E4567-E89B-42D3-A456-426614174000")
        self.assertIsNone(session_uuid("active"))

    def test_publisher_uses_display_state_not_object_identity(self):
        class Result:
            returncode = 0
        class State:
            display_state = "working"
            agent = "codex"
            project_basename = "bridge"
            children = set()
        from unittest.mock import patch
        with patch("agent_terminal_bridge.publisher.find_it2", return_value="/bin/true"), patch("agent_terminal_bridge.publisher.subprocess.run", return_value=Result()) as run:
            self.assertTrue(publish("w0t0p0:123e4567-e89b-42d3-a456-426614174000", State()))
        self.assertIn("working", run.call_args.args[0])

    def test_doctor_does_not_call_stale_socket_ready(self):
        from unittest.mock import patch
        with patch("agent_terminal_bridge.cli.send", return_value={"status": "unavailable"}):
            self.assertFalse(socket_ready())

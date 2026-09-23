import unittest

from agent_terminal_bridge.protocol import ProtocolError, validate_event, validate_register
from agent_terminal_bridge.server import Bridge


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

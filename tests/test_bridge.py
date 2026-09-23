import unittest

from agent_terminal_bridge.protocol import ProtocolError, validate_event, validate_register
from agent_terminal_bridge.server import Bridge
from agent_terminal_bridge.publisher import session_uuid, publish
from agent_terminal_bridge.cli import socket_ready
from agent_terminal_bridge.config import command, publish as publish_config, render_json, render_kimi
from agent_terminal_bridge.adapters import mapping


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

    def test_json_publishers_preserve_unrelated_configuration(self):
        settings = {"permissions": {"allow": ["Bash(git)"]}}
        rendered, changed = render_json("claude", settings)
        self.assertTrue(changed)
        self.assertEqual(rendered["permissions"], settings["permissions"])
        self.assertIn(command("claude"), str(rendered))
        repeated, changed = render_json("claude", rendered)
        self.assertFalse(changed)
        self.assertEqual(repeated, rendered)

    def test_kimi_publisher_is_marked_and_repeat_safe(self):
        rendered, changed = render_kimi('default_model = "kimi"\n')
        self.assertTrue(changed)
        self.assertIn('# agent-terminal-bridge:kimi', rendered)
        repeated, changed = render_kimi(rendered)
        self.assertFalse(changed)
        self.assertEqual(repeated, rendered)

    def test_publish_dry_run_does_not_write(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as temporary:
            home = Path(temporary)
            outcome = publish_config("cursor", home=home, dry_run=True)
            self.assertTrue(outcome["changed"])
            self.assertFalse((home / ".cursor/hooks.json").exists())

    def test_installed_completion_events_are_mapped(self):
        for agent, upstream in (("claude", "SessionEnd"), ("cursor", "sessionEnd"), ("kimi", "SessionEnd")):
            self.assertEqual(mapping(agent)[1][upstream], "session_closed")

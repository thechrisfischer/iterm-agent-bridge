import asyncio
import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent_terminal_bridge.protocol import ProtocolError, validate_event, validate_register
from agent_terminal_bridge.server import Bridge, serve, socket_path
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
        self.assertIn('event = "SessionStart"', rendered)
        self.assertNotIn('event = "TurnStarted"', rendered)
        repeated, changed = render_kimi(rendered)
        self.assertFalse(changed)
        self.assertEqual(repeated, rendered)

    def test_kimi_publisher_replaces_only_its_legacy_hook_blocks(self):
        legacy = ('custom = "value"\n\n# agent-terminal-bridge:kimi\n[[hooks]]\n'
                  'event = "TurnStarted"\ncommand = "agent-terminal-bridge emit --agent kimi"\n'
                  'timeout = 1\n\n[[hooks]]\nevent = "Stop"\ncommand = "other-hook"\n')
        rendered, changed = render_kimi(legacy)
        self.assertTrue(changed)
        self.assertIn('custom = "value"', rendered)
        self.assertIn('command = "other-hook"', rendered)
        self.assertNotIn('event = "TurnStarted"', rendered)

    def test_kimi_publisher_refuses_invalid_existing_configuration(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as temporary:
            home = Path(temporary)
            path = home / ".kimi-code/config.toml"
            path.parent.mkdir()
            path.write_text("not = [valid\n")
            class Result:
                returncode = 1
            with patch("agent_terminal_bridge.config.shutil.which", return_value="/fake/kimi"), \
                 patch("agent_terminal_bridge.config.subprocess.run", return_value=Result()):
                with self.assertRaises(ValueError):
                    publish_config("kimi", home=home)
            self.assertEqual(path.read_text(), "not = [valid\n")

    def test_kimi_publisher_validates_staged_configuration(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as temporary:
            home = Path(temporary)
            class Result:
                returncode = 0
            with patch("agent_terminal_bridge.config.shutil.which", return_value="/fake/kimi"), \
                 patch("agent_terminal_bridge.config.subprocess.run", return_value=Result()) as run:
                publish_config("kimi", home=home)
            self.assertEqual(run.call_count, 1)
            self.assertTrue((home / ".kimi-code/config.toml").exists())

    def test_publish_dry_run_does_not_write(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as temporary:
            home = Path(temporary)
            outcome = publish_config("cursor", home=home, dry_run=True)
            self.assertTrue(outcome["changed"])
            self.assertFalse((home / ".cursor/hooks.json").exists())

    def test_emit_ignores_malformed_hook_input(self):
        from io import StringIO
        from unittest.mock import patch
        from agent_terminal_bridge.cli import main
        with patch("sys.stdin", StringIO("{")), patch("sys.stdout", new_callable=StringIO) as output:
            self.assertEqual(main(["emit", "--agent", "kimi"]), 0)
        self.assertEqual(output.getvalue(), "{}\n")

    def test_installed_completion_events_are_mapped(self):
        for agent, upstream in (("claude", "SessionEnd"), ("cursor", "sessionEnd"), ("kimi", "SessionEnd")):
            self.assertEqual(mapping(agent)[1][upstream], "session_closed")


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_server_removes_its_socket(self):
        with TemporaryDirectory() as temporary, patch.dict(os.environ, {"XDG_CONFIG_HOME": temporary}):
            task = asyncio.create_task(serve())
            for _ in range(50):
                if socket_path().exists():
                    break
                await asyncio.sleep(.01)
            self.assertTrue(socket_path().exists())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertFalse(socket_path().exists())

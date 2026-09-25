import asyncio
import curses
import os
import subprocess
import unittest
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent_terminal_bridge.protocol import ProtocolError, validate_event, validate_register
from agent_terminal_bridge.server import Bridge, serve, socket_path
from agent_terminal_bridge.publisher import session_uuid, publish
from agent_terminal_bridge.cli import launch, socket_ready
from agent_terminal_bridge.cockpit import CockpitError, create as create_cockpit
from agent_terminal_bridge.config import command, publish as publish_config, render_json, render_kimi
from agent_terminal_bridge.adapters import mapping
from agent_terminal_bridge.review import _ReviewUI, discover_repositories, render_review


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

    def test_snapshot_lists_only_privacy_limited_child_identity(self):
        bridge=Bridge(publisher=lambda session, state: True)
        bridge.handle(registration())
        bridge.handle(event("child_started", 0, child_id="child-7"))
        snapshot = bridge.handle({"type": "snapshot"})["sessions"]
        self.assertEqual(snapshot[0]["children"], ["child-7"])
        self.assertNotIn("nonce", snapshot[0])

    def test_review_reports_a_non_git_directory(self):
        with TemporaryDirectory() as temporary:
            self.assertIn("No Git worktree", render_review(temporary))

    def test_review_discovers_nested_repositories_and_marks_dirty_state(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            clean = root / "clean-repo"
            dirty = root / "dirty-repo"
            for repo in (clean, dirty):
                repo.mkdir()
                subprocess.run(["git", "init", "-q", str(repo)], check=True)
                subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
                subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
                (repo / "README.md").write_text("initial\n")
                subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
                subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "initial"], check=True)
            (dirty / "README.md").write_text("changed\n")

            repos = discover_repositories(root)
            self.assertEqual([repo.path.name for repo in repos], ["clean-repo", "dirty-repo"])
            self.assertFalse(repos[0].dirty)
            self.assertTrue(repos[1].dirty)
            self.assertIn("2 repos", render_review(root))
            self.assertIn("1 changed", render_review(root))

    def test_review_ctrl_w_switches_between_repo_and_diff_focus(self):
        class Window:
            def getmaxyx(self):
                return (24, 80)

        ui = object.__new__(_ReviewUI)
        ui.window = Window()
        ui.repos = (object(),)
        ui.selected = 0
        ui.focus = "repos"
        ui.diff = ["@@ -1 +1 @@"]
        ui.diff_scroll = 0
        ui.prefix = False
        ui.message = ""

        self.assertTrue(ui.handle(23))
        self.assertTrue(ui.prefix)
        self.assertTrue(ui.handle(curses.KEY_DOWN))
        self.assertEqual(ui.focus, "diff")
        self.assertTrue(ui.handle(23))
        self.assertTrue(ui.handle(curses.KEY_UP))
        self.assertEqual(ui.focus, "repos")

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

    def test_launch_starts_the_service_before_registration(self):
        args = Namespace(agent="codex", command=["--", "/bin/true"])
        with patch.dict(os.environ, {"ITERM_SESSION_ID": "w0t0p0:123e4567-e89b-42d3-a456-426614174000"}), \
             patch("agent_terminal_bridge.cli.socket_ready", side_effect=[False, True]), \
             patch("agent_terminal_bridge.cli.subprocess.Popen") as start, \
             patch("agent_terminal_bridge.cli.send", return_value={"status": "registered"}) as send, \
             patch("agent_terminal_bridge.cli.subprocess.call", return_value=0):
            self.assertEqual(launch(args), 0)
        self.assertTrue(start.called)
        self.assertEqual(send.call_args.args[0]["type"], "register")

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

    def test_cockpit_creates_review_and_flightboard_in_new_panes(self):
        class Result:
            returncode = 0
            stderr = ""

            def __init__(self, sessions):
                self.stdout = __import__("json").dumps([{"id": value} for value in sessions])

        source = "123E4567-E89B-42D3-A456-426614174000"
        sessions = [[source], [source], [source, "review"], [source, "review"], [source, "review", "flightboard"]]
        calls = []

        def run(command, **_kwargs):
            calls.append(command)
            if command[2:4] == ["list", "--json"]:
                return Result(sessions.pop(0))
            return Result([])

        with patch("agent_terminal_bridge.cockpit.find_it2", return_value="/fake/it2"), \
             patch("agent_terminal_bridge.cockpit.subprocess.run", side_effect=run):
            panes = create_cockpit("window:%s" % source)
        self.assertEqual(panes, {"review": "review", "flightboard": "flightboard"})
        self.assertIn(["/fake/it2", "session", "split", "--session", source, "--vertical"], calls)
        self.assertIn(["/fake/it2", "session", "split", "--session", "review"], calls)
        self.assertIn(["/fake/it2", "session", "run", "exec agent-terminal-bridge review --watch", "--session", "review"], calls)
        self.assertIn(["/fake/it2", "session", "run", "exec agent-terminal-bridge agents --watch", "--session", "flightboard"], calls)

    def test_cockpit_refuses_to_create_panes_without_an_iterm_session(self):
        with self.assertRaises(CockpitError):
            create_cockpit("not-an-iterm-session")

    def test_cockpit_reports_watcher_failure_after_leaving_created_panes_alone(self):
        class Result:
            def __init__(self, sessions=(), returncode=0, stderr=""):
                self.returncode = returncode
                self.stderr = stderr
                self.stdout = __import__("json").dumps([{"id": value} for value in sessions])

        source = "123E4567-E89B-42D3-A456-426614174000"
        snapshots = [[source], [source], [source, "review"], [source, "review"], [source, "review", "flightboard"]]
        calls = []

        def run(command, **_kwargs):
            calls.append(command)
            if command[2:4] == ["list", "--json"]:
                return Result(snapshots.pop(0))
            if command[2:4] == ["run", "exec agent-terminal-bridge agents --watch"]:
                return Result(returncode=1, stderr="profile rejected command")
            return Result()

        with patch("agent_terminal_bridge.cockpit.find_it2", return_value="/fake/it2"), \
             patch("agent_terminal_bridge.cockpit.subprocess.run", side_effect=run):
            with self.assertRaisesRegex(CockpitError, "profile rejected command"):
                create_cockpit("window:%s" % source)
        self.assertIn(["/fake/it2", "session", "split", "--session", "review"], calls)
        self.assertIn(["/fake/it2", "session", "run", "exec agent-terminal-bridge review --watch", "--session", "review"], calls)


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

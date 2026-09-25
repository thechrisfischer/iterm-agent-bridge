import argparse
import asyncio
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .adapters import ADAPTERS, mapping
from .protocol import PROTOCOL_VERSION
from .server import config_dir, socket_path, serve
from .publisher import find_it2
from .cockpit import CockpitError, create as create_cockpit
from .config import JSON_AGENTS, publish
from .review import render_patch, render_review, run_review_ui


def send(body):
    import socket
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(.5); client.connect(str(socket_path()))
            client.sendall((json.dumps(body)+"\n").encode())
            return json.loads(client.makefile("rb").readline().decode())
    except OSError: return {"status": "unavailable"}


def socket_ready():
    """A stale Unix-socket pathname is not evidence that a server is alive."""
    return send({"type": "probe"}).get("status") != "unavailable"


def ensure_server():
    """Start the local service on first iTerm launch; never block the agent."""
    if socket_ready(): return True
    try:
        config_dir().mkdir(mode=0o700, parents=True, exist_ok=True)
        with open(os.devnull, "wb") as null:
            subprocess.Popen([sys.executable, "-m", "agent_terminal_bridge", "serve"], stdin=null, stdout=null, stderr=null, start_new_session=True)
    except OSError: return False
    for _ in range(10):
        time.sleep(.05)
        if socket_ready(): return True
    return False


def launch(args):
    session = os.environ.get("ITERM_SESSION_ID")
    if not session: print("ITERM_SESSION_ID is required", file=sys.stderr); return 2
    ensure_server()
    nonce = secrets.token_hex(16)
    send({"type":"register","protocol_version":1,"agent":args.agent,"iterm_session_id":session,"launch_nonce":nonce,"project_basename":Path.cwd().name})
    env = os.environ.copy(); env["AGENT_TERMINAL_BRIDGE_NONCE"] = nonce
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command: print("an agent command is required after --", file=sys.stderr); return 2
    return subprocess.call(command, env=env)


def emit(args):
    _, events = mapping(args.agent)
    try: raw = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except (OSError, ValueError): print("{}"); return 0
    if not isinstance(raw, dict): print("{}"); return 0
    kind = events.get(raw.get("hook_event_name") or args.upstream_event)
    session, nonce = os.environ.get("ITERM_SESSION_ID"), os.environ.get("AGENT_TERMINAL_BRIDGE_NONCE")
    if not kind or not session or not nonce: print("{}"); return 0
    seqfile = config_dir() / ("sequence-" + nonce); config_dir().mkdir(mode=0o700, parents=True, exist_ok=True)
    try: sequence = int(seqfile.read_text()) + 1
    except (OSError, ValueError): sequence = 0
    seqfile.write_text(str(sequence))
    body={"type":"event","protocol_version":PROTOCOL_VERSION,"agent":args.agent,"iterm_session_id":session,"launch_nonce":nonce,"event_id":str(uuid.uuid4()),"sequence":sequence,"kind":kind}
    if kind in ("child_started","child_finished"): body["child_id"] = str(raw.get("agent_id") or raw.get("task_id") or "unknown")
    send(body); print("{}"); return 0


def render_agents():
    reply = send({"type": "snapshot"})
    sessions = reply.get("sessions", [])
    lines = ["Background agents"]
    if not sessions: return "\n".join(lines + ["\nNo active bridge sessions."])
    for state in sessions:
        lines.append("\n%s · %s · %s" % (state["agent"], state["project"], state["state"]))
        children = state["children"]
        lines.extend(["  child %s · working" % child for child in children] or ["  no reported child agents"])
    return "\n".join(lines)


def watch(render, seconds):
    try:
        while True:
            sys.stdout.write("\033[H\033[J" + render() + "\n")
            sys.stdout.flush(); time.sleep(seconds)
    except KeyboardInterrupt: return 0


def main(argv=None):
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="action",required=True)
    sub.add_parser("serve"); sub.add_parser("doctor")
    install = sub.add_parser("install"); install.add_argument("--dry-run", action="store_true"); install.add_argument("--agent", choices=tuple(sorted(JSON_AGENTS | {"kimi"})))
    l=sub.add_parser("launch"); l.add_argument("--agent",choices=ADAPTERS,required=True); l.add_argument("command",nargs=argparse.REMAINDER)
    e=sub.add_parser("emit"); e.add_argument("--agent",choices=ADAPTERS,required=True); e.add_argument("--upstream-event")
    review = sub.add_parser("review"); review.add_argument("--patch", action="store_true"); review.add_argument("--watch", action="store_true"); review.add_argument("--interval", type=float, default=2); review.add_argument("--root", default=".")
    agents = sub.add_parser("agents"); agents.add_argument("--watch", action="store_true"); agents.add_argument("--interval", type=float, default=2)
    cockpit = sub.add_parser("cockpit", help="open read-only Git review and background-agent panes in iTerm2")
    cockpit.add_argument("--review-only", action="store_true", help="open only the Git review pane")
    a=p.parse_args(argv)
    if a.action=="serve": asyncio.run(serve()); return 0
    if a.action=="launch": return launch(a)
    if a.action=="emit": return emit(a)
    if a.action=="review":
        render = (lambda: render_patch(a.root)) if a.patch else (lambda: render_review(a.root))
        if a.watch:
            if not a.patch and sys.stdin.isatty() and sys.stdout.isatty():
                return run_review_ui(a.root, max(a.interval, .2))
            return watch(render, max(a.interval, .2))
        print(render()); return 0
    if a.action=="agents":
        if a.watch: return watch(render_agents, max(a.interval, .2))
        print(render_agents()); return 0
    if a.action=="cockpit":
        try:
            panes = create_cockpit(os.environ.get("ITERM_SESSION_ID"), include_flightboard=not a.review_only)
        except CockpitError as exc:
            print("cockpit: %s" % exc, file=sys.stderr); return 2
        if a.review_only:
            print("Opened review pane %s." % panes["review"])
        else:
            print("Opened review pane %s and background-agent pane %s." % (panes["review"], panes["flightboard"]))
        return 0
    if a.action=="install":
        if a.agent:
            result = publish(a.agent, dry_run=a.dry_run); action = "Would add" if a.dry_run and result["changed"] else ("Added" if result["changed"] else "Already has")
            print("%s bridge hooks for %s at %s" % (action, a.agent, result["path"])); return 0
        if a.dry_run: print("Would create %s and install no hooks until you review them." % config_dir())
        else: config_dir().mkdir(mode=0o700, parents=True, exist_ok=True); print("Created bridge state directory. Enable iTerm2 Python API and install a reviewed adapter hook manually.")
        return 0
    print("socket=" + ("ready" if socket_ready() else "not_configured")); print("iterm2=" + ("found" if find_it2() else "missing"))
    for name,(exe,events) in ADAPTERS.items(): print("%s executable=%s events=%s"%(name,"found" if shutil.which(exe) else "missing",len(events)))
    return 0


if __name__ == "__main__": raise SystemExit(main())

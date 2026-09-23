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
from .config import JSON_AGENTS, publish


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
    if socket_ready():
        return True
    try:
        config_dir().mkdir(mode=0o700, parents=True, exist_ok=True)
        with open(os.devnull, "wb") as null:
            subprocess.Popen(
                [sys.executable, "-m", "agent_terminal_bridge", "serve"],
                stdin=null, stdout=null, stderr=null, start_new_session=True,
            )
    except OSError:
        return False
    for _ in range(10):
        time.sleep(.05)
        if socket_ready():
            return True
    return False


def launch(args):
    session = os.environ.get("ITERM_SESSION_ID")
    if not session: print("ITERM_SESSION_ID is required", file=sys.stderr); return 2
    ensure_server()
    nonce = secrets.token_hex(16)
    send({"type":"register","protocol_version":1,"agent":args.agent,"iterm_session_id":session,"launch_nonce":nonce,"project_basename":Path.cwd().name})
    env = os.environ.copy(); env["AGENT_TERMINAL_BRIDGE_NONCE"] = nonce
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        print("an agent command is required after --", file=sys.stderr)
        return 2
    return subprocess.call(command, env=env)


def emit(args):
    _, events = mapping(args.agent)
    try:
        raw = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except (OSError, ValueError):
        print("{}")
        return 0
    if not isinstance(raw, dict):
        print("{}")
        return 0
    kind = events.get(raw.get("hook_event_name") or args.upstream_event)
    session, nonce = os.environ.get("ITERM_SESSION_ID"), os.environ.get("AGENT_TERMINAL_BRIDGE_NONCE")
    if not kind or not session or not nonce:
        print("{}")
        return 0
    seqfile = config_dir() / ("sequence-" + nonce); config_dir().mkdir(mode=0o700, parents=True, exist_ok=True)
    try: sequence = int(seqfile.read_text()) + 1
    except (OSError, ValueError): sequence = 0
    seqfile.write_text(str(sequence))
    body={"type":"event","protocol_version":PROTOCOL_VERSION,"agent":args.agent,"iterm_session_id":session,"launch_nonce":nonce,"event_id":str(uuid.uuid4()),"sequence":sequence,"kind":kind}
    if kind in ("child_started","child_finished"): body["child_id"] = str(raw.get("agent_id") or raw.get("task_id") or "unknown")
    send(body)
    print("{}")
    return 0


def main(argv=None):
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="action",required=True)
    sub.add_parser("serve"); sub.add_parser("doctor")
    install = sub.add_parser("install"); install.add_argument("--dry-run", action="store_true"); install.add_argument("--agent", choices=tuple(sorted(JSON_AGENTS | {"kimi"})))
    l=sub.add_parser("launch"); l.add_argument("--agent",choices=ADAPTERS,required=True); l.add_argument("command",nargs=argparse.REMAINDER)
    e=sub.add_parser("emit"); e.add_argument("--agent",choices=ADAPTERS,required=True); e.add_argument("--upstream-event")
    a=p.parse_args(argv)
    if a.action=="serve": asyncio.run(serve()); return 0
    if a.action=="launch": return launch(a)
    if a.action=="emit": return emit(a)
    if a.action=="install":
        if a.agent:
            result = publish(a.agent, dry_run=a.dry_run)
            action = "Would add" if a.dry_run and result["changed"] else ("Added" if result["changed"] else "Already has")
            print("%s bridge hooks for %s at %s" % (action, a.agent, result["path"]))
            return 0
        if a.dry_run:
            print("Would create %s and install no hooks until you review them." % config_dir())
        else:
            config_dir().mkdir(mode=0o700, parents=True, exist_ok=True)
            print("Created bridge state directory. Enable iTerm2 Python API and install a reviewed adapter hook manually.")
        return 0
    print("socket=" + ("ready" if socket_ready() else "not_configured"))
    print("iterm2=" + ("found" if find_it2() else "missing"))
    for name,(exe,events) in ADAPTERS.items(): print("%s executable=%s events=%s"%(name,"found" if shutil.which(exe) else "missing",len(events)))
    return 0


if __name__ == "__main__": raise SystemExit(main())

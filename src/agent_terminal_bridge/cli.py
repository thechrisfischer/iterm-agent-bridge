import argparse
import asyncio
import json
import os
import secrets
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from .adapters import ADAPTERS, mapping
from .protocol import PROTOCOL_VERSION
from .server import config_dir, socket_path, serve


def send(body):
    import socket
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(.5); client.connect(str(socket_path()))
            client.sendall((json.dumps(body)+"\n").encode())
            return json.loads(client.makefile("rb").readline().decode())
    except OSError: return {"status": "unavailable"}


def launch(args):
    session = os.environ.get("ITERM_SESSION_ID")
    if not session: print("ITERM_SESSION_ID is required", file=sys.stderr); return 2
    nonce = secrets.token_hex(16)
    send({"type":"register","protocol_version":1,"agent":args.agent,"iterm_session_id":session,"launch_nonce":nonce,"project_basename":Path.cwd().name})
    env = os.environ.copy(); env["AGENT_TERMINAL_BRIDGE_NONCE"] = nonce
    return subprocess.call(args.command, env=env)


def emit(args):
    _, events = mapping(args.agent)
    raw = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    kind = events.get(raw.get("hook_event_name") or args.upstream_event)
    session, nonce = os.environ.get("ITERM_SESSION_ID"), os.environ.get("AGENT_TERMINAL_BRIDGE_NONCE")
    if not kind or not session or not nonce: return 0
    seqfile = config_dir() / ("sequence-" + nonce); config_dir().mkdir(mode=0o700, parents=True, exist_ok=True)
    try: sequence = int(seqfile.read_text()) + 1
    except (OSError, ValueError): sequence = 0
    seqfile.write_text(str(sequence))
    body={"type":"event","protocol_version":PROTOCOL_VERSION,"agent":args.agent,"iterm_session_id":session,"launch_nonce":nonce,"event_id":str(uuid.uuid4()),"sequence":sequence,"kind":kind}
    if kind in ("child_started","child_finished"): body["child_id"] = str(raw.get("agent_id") or raw.get("task_id") or "unknown")
    send(body); return 0


def main(argv=None):
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="action",required=True)
    sub.add_parser("serve"); d=sub.add_parser("doctor")
    l=sub.add_parser("launch"); l.add_argument("--agent",choices=ADAPTERS,required=True); l.add_argument("command",nargs=argparse.REMAINDER)
    e=sub.add_parser("emit"); e.add_argument("--agent",choices=ADAPTERS,required=True); e.add_argument("--upstream-event")
    a=p.parse_args(argv)
    if a.action=="serve": asyncio.run(serve()); return 0
    if a.action=="launch": return launch(a)
    if a.action=="emit": return emit(a)
    print("socket=" + ("ready" if socket_path().exists() else "not_configured"))
    for name,(exe,events) in ADAPTERS.items(): print("%s executable=%s events=%s"%(name,"found" if shutil.which(exe) else "missing",len(events)))
    return 0


if __name__ == "__main__": raise SystemExit(main())

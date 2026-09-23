"""Local Unix socket bridge. Publisher is intentionally optional."""

import asyncio
import json
import os
from pathlib import Path

from .protocol import ProtocolError, validate_event, validate_register
from .state import SessionState


def config_dir():
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "agent-terminal-bridge"


def socket_path():
    return config_dir() / "bridge.sock"


class Bridge:
    def __init__(self):
        self.sessions = {}

    def handle(self, raw):
        if raw.get("type") == "register":
            data = validate_register(raw)
            self.sessions[data["iterm_session_id"]] = SessionState(data["agent"], data["iterm_session_id"], data["launch_nonce"], data["project_basename"], delivery="ready")
            return {"status": "registered"}
        if raw.get("type") == "event":
            data = validate_event(raw)
            state = self.sessions.get(data["iterm_session_id"])
            if state is None or state.nonce != data["launch_nonce"]:
                raise ProtocolError("unregistered or stale session")
            state.apply(data)
            return {"status": "accepted", "state": state.display_state}
        raise ProtocolError("unsupported message type")


async def serve():
    path = socket_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists(): path.unlink()
    bridge = Bridge()
    async def handler(reader, writer):
        try:
            raw = json.loads((await asyncio.wait_for(reader.readline(), .5)).decode())
            result = bridge.handle(raw)
        except Exception as exc:
            result = {"status": "rejected", "reason": str(exc)}
        writer.write((json.dumps(result) + "\n").encode())
        await writer.drain(); writer.close(); await writer.wait_closed()
    server = await asyncio.start_unix_server(handler, path=str(path))
    os.chmod(path, 0o600)
    async with server: await server.serve_forever()

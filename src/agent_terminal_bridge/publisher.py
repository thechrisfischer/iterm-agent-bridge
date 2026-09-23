"""Best-effort publisher for iTerm2's native Session Status sidebar."""

import os
import re
import shutil
import subprocess
from pathlib import Path

COLORS = {"idle": "#98c379", "working": "#e5a950", "waiting": "#e06c75"}
SESSION_RE = re.compile(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}$")


def session_uuid(value):
    """Return the explicit UUID portion of ITERM_SESSION_ID, if valid."""
    candidate = str(value or "").rsplit(":", 1)[-1]
    return candidate.upper() if SESSION_RE.fullmatch(candidate) else None


def find_it2(environ=None):
    environ = os.environ if environ is None else environ
    choices = [environ.get("AGENT_TERMINAL_BRIDGE_IT2"), shutil.which("it2"),
               "/Applications/iTerm.app/Contents/Resources/utilities/it2"]
    for value in choices:
        if value and Path(value).is_file() and os.access(value, os.X_OK):
            return str(Path(value))
    return None


def publish(session_id, state, timeout=0.8, environ=None):
    """Write one status update to iTerm2; return whether iTerm accepted it."""
    terminal = session_uuid(session_id)
    it2 = find_it2(environ)
    if not terminal or not it2 or state.display_state not in COLORS:
        return False
    detail = "%s · %s" % (state.agent.capitalize(), state.project_basename)
    command = [it2, "session", "set-status", "--session", terminal,
               "--status", state.display_state, "--dot-color", COLORS[state.display_state],
               "--text-color", COLORS[state.display_state], "--detail", detail,
               "--background-tasks", str(len(state.children))]
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=timeout, check=False)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False

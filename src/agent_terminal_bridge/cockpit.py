"""Create a small, explicit iTerm2 code-review cockpit."""

import json
import subprocess

from .publisher import find_it2, session_uuid


class CockpitError(RuntimeError):
    """iTerm2 could not safely create the requested pane layout."""


def _sessions(it2):
    """Return the currently visible iTerm session IDs, or explain the failure."""
    try:
        result = subprocess.run([it2, "session", "list", "--json"], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CockpitError("could not read iTerm2 sessions: %s" % exc)
    if result.returncode:
        raise CockpitError("iTerm2 could not list sessions: %s" % result.stderr.strip())
    try:
        records = json.loads(result.stdout)
        return {record["id"] for record in records if isinstance(record, dict) and isinstance(record.get("id"), str)}
    except (TypeError, ValueError) as exc:
        raise CockpitError("iTerm2 returned an invalid session list: %s" % exc)


def _command(it2, arguments):
    try:
        result = subprocess.run([it2] + arguments, text=True, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CockpitError("iTerm2 command failed: %s" % exc)
    if result.returncode:
        raise CockpitError("iTerm2 command failed: %s" % result.stderr.strip())


def _split(it2, source, vertical):
    before = _sessions(it2)
    arguments = ["session", "split", "--session", source]
    if vertical:
        arguments.append("--vertical")
    _command(it2, arguments)
    created = _sessions(it2) - before
    if len(created) != 1:
        raise CockpitError("iTerm2 created an ambiguous pane layout; no watcher was started")
    return created.pop()


def create(session_id, environ=None, include_flightboard=True):
    """Create review and optionally flightboard panes adjacent to ``session_id``.

    The iTerm CLI inherits the source pane's working directory for both splits.
    It receives only fixed local commands; no terminal content is inspected.
    """
    source = session_uuid(session_id)
    if not source:
        raise CockpitError("cockpit must be run from an iTerm2 session")
    it2 = find_it2(environ)
    if not it2:
        raise CockpitError("iTerm2 CLI was not found")
    if source not in _sessions(it2):
        raise CockpitError("the current iTerm2 session is no longer available")

    review = _split(it2, source, vertical=True)
    _command(it2, ["session", "run", "exec agent-terminal-bridge review --watch", "--session", review])
    if not include_flightboard:
        return {"review": review}
    flightboard = _split(it2, review, vertical=False)
    _command(it2, ["session", "run", "exec agent-terminal-bridge agents --watch", "--session", flightboard])
    return {"review": review, "flightboard": flightboard}

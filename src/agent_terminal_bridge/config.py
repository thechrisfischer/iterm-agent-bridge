"""Conservative, owned hook-entry publishers for supported agent configs."""

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


COMMAND = "agent-terminal-bridge emit --agent "
JSON_AGENTS = frozenset(("claude", "cursor", "agy"))
KIMI_EVENTS = ("TurnStarted", "PreToolUse", "PostToolUse", "PermissionRequest",
               "PermissionResult", "Stop", "SubagentStart", "SubagentStop", "SessionEnd")
EVENTS = {
    "claude": ("UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest",
               "Stop", "SubagentStart", "SubagentStop", "SessionEnd"),
    "cursor": ("beforeSubmitPrompt", "preToolUse", "postToolUse", "subagentStart",
               "subagentStop", "stop", "sessionEnd"),
    "agy": ("PreInvocation", "PreToolUse", "PostToolUse", "Stop"),
}


def command(agent):
    return COMMAND + agent


def config_path(agent, home=None):
    home = Path.home() if home is None else Path(home)
    paths = {
        "claude": home / ".claude/settings.json",
        "cursor": home / ".cursor/hooks.json",
        "agy": home / ".gemini/config/hooks.json",
        "kimi": home / ".kimi-code/config.toml",
    }
    return paths[agent]


def _load_json(path):
    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_file():
        raise ValueError("refusing non-regular configuration: %s" % path)
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError("invalid JSON configuration: %s" % path) from exc
    if not isinstance(value, dict):
        raise ValueError("configuration root must be an object: %s" % path)
    return value


def _has_command(value, expected):
    if isinstance(value, dict):
        return any(_has_command(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(_has_command(item, expected) for item in value)
    return value == expected


def render_json(agent, existing):
    """Return a merged copy, without changing an existing matching command."""
    output = json.loads(json.dumps(existing))
    expected = command(agent)
    changed = False
    if agent == "claude":
        hooks = output.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise ValueError("Claude hooks must be an object")
        for event in EVENTS[agent]:
            rules = hooks.setdefault(event, [])
            if not isinstance(rules, list):
                raise ValueError("Claude hook event %s must be an array" % event)
            if not _has_command(rules, expected):
                rules.append({"matcher": "", "hooks": [{"type": "command", "command": expected, "timeout": 1}]})
                changed = True
    elif agent == "cursor":
        if "version" not in output:
            output["version"] = 1
            changed = True
        if output.get("version") != 1:
            raise ValueError("Cursor hooks version must be 1")
        hooks = output.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise ValueError("Cursor hooks must be an object")
        for event in EVENTS[agent]:
            rules = hooks.setdefault(event, [])
            if not isinstance(rules, list):
                raise ValueError("Cursor hook event %s must be an array" % event)
            if not _has_command(rules, expected):
                rules.append({"command": expected, "timeout": 1, "failClosed": False})
                changed = True
    elif agent == "agy":
        section = output.setdefault("agent-terminal-bridge", {})
        if not isinstance(section, dict):
            raise ValueError("Antigravity bridge hook name conflicts with non-object")
        for event in EVENTS[agent]:
            rules = section.setdefault(event, [])
            if not isinstance(rules, list):
                raise ValueError("Antigravity hook event %s must be an array" % event)
            if not _has_command(rules, expected):
                if event in ("PreToolUse", "PostToolUse"):
                    rules.append({"matcher": "*", "hooks": [{"type": "command", "command": expected, "timeout": 1}]})
                else:
                    rules.append({"type": "command", "command": expected, "timeout": 1})
                changed = True
    else:
        raise ValueError("unsupported JSON agent: %s" % agent)
    return output, changed


def render_kimi(existing):
    marker = "# agent-terminal-bridge:kimi"
    if marker in existing or command("kimi") in existing:
        return existing, False
    lines = ["", marker]
    for event in KIMI_EVENTS:
        lines.extend(("[[hooks]]", 'event = "%s"' % event,
                      'command = "%s"' % command("kimi"), "timeout = 1", ""))
    return existing.rstrip() + "\n" + "\n".join(lines), True


def _validate_kimi(path):
    """Delegate TOML validation to the installed Kimi CLI; never guess TOML."""
    kimi = shutil.which("kimi")
    if not kimi:
        raise ValueError("Kimi CLI is required to validate Kimi configuration")
    try:
        result = subprocess.run([kimi, "doctor", "config", str(path)],
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("could not validate Kimi configuration") from exc
    if result.returncode:
        raise ValueError("invalid Kimi configuration: %s" % path)


def publish(agent, home=None, dry_run=False):
    path = config_path(agent, home)
    if agent in JSON_AGENTS:
        rendered, changed = render_json(agent, _load_json(path))
        content = json.dumps(rendered, indent=2, sort_keys=True) + "\n"
        json.loads(content)
    elif agent == "kimi":
        if path.exists() and (path.is_symlink() or not path.is_file()):
            raise ValueError("refusing non-regular configuration: %s" % path)
        existing = path.read_text() if path.exists() else ""
        if path.exists():
            _validate_kimi(path)
        rendered, changed = render_kimi(existing)
        content = rendered
    else:
        raise ValueError("unsupported agent: %s" % agent)
    if not changed or dry_run:
        return {"path": str(path), "changed": changed, "backup": None}
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = None
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
        os.chmod(temporary, 0o600)
        if agent == "kimi":
            _validate_kimi(temporary)
        # Validate the staged candidate before making a recovery copy or
        # replacing the user's configuration.
        if path.exists():
            backup = path.with_name(path.name + ".agent-terminal-bridge.%d.bak" % time.time_ns())
            shutil.copy2(path, backup)
            if not backup.is_file() or backup.read_bytes() != path.read_bytes():
                raise OSError("could not verify configuration backup")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"path": str(path), "changed": True, "backup": str(backup) if backup else None}

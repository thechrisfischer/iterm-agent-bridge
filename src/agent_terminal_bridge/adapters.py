"""Documented mappings; no transcript or terminal parsing."""

ADAPTERS = {
    "claude": ("claude", {"UserPromptSubmit": "turn_started", "PreToolUse": "tool_started", "PostToolUse": "tool_finished", "PermissionRequest": "permission_requested", "Stop": "turn_finished", "SubagentStart": "child_started", "SubagentStop": "child_finished", "SessionEnd": "session_closed"}),
    "codex": ("codex", {"UserPromptSubmit": "turn_started", "PreToolUse": "tool_started", "PostToolUse": "tool_finished", "PermissionRequest": "permission_requested", "Stop": "turn_finished", "SubagentStart": "child_started", "SubagentStop": "child_finished", "SessionEnd": "session_closed"}),
    "cursor": ("agent", {"beforeSubmitPrompt": "turn_started", "preToolUse": "tool_started", "postToolUse": "tool_finished", "stop": "turn_finished", "subagentStart": "child_started", "subagentStop": "child_finished", "sessionEnd": "session_closed"}),
    "kimi": ("kimi", {"SessionStart": "turn_started", "UserPromptSubmit": "turn_started", "PreToolUse": "tool_started", "PostToolUse": "tool_finished", "PostToolUseFailure": "tool_finished", "PermissionRequest": "permission_requested", "PermissionResult": "permission_resolved", "Stop": "turn_finished", "StopFailure": "interrupted", "Interrupt": "interrupted", "SubagentStart": "child_started", "SubagentStop": "child_finished", "SessionEnd": "session_closed"}),
    "agy": ("agy", {"PreInvocation": "turn_started", "PreToolUse": "tool_started", "PostToolUse": "tool_finished", "Stop": "turn_finished"}),
}


def mapping(name):
    try:
        return ADAPTERS[name]
    except KeyError:
        raise ValueError("unsupported agent: %s" % name)

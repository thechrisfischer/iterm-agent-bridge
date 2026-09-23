# Agent Terminal Bridge

Agent Terminal Bridge publishes privacy-safe lifecycle state to iTerm2's native
**Session Status** sidebar. It has normalized adapter definitions for Claude
Code, Codex CLI, Cursor Agent, Kimi Code, and Antigravity CLI.

It turns documented agent lifecycle events into four honest states:
`working`, `waiting`, `idle`, and `unavailable`. It does not read prompts,
terminal output, transcripts, command arguments, or credentials; it does not
approve, block, or otherwise affect agent actions.

## Requirements

- macOS with iTerm2 3.7 or later and its CLI API available.
- Python 3.9 or later.

Enable the Session Status toolbelt in iTerm2: **View → Toggle Toolbelt →
Session Status**. The bridge addresses the exact `ITERM_SESSION_ID` supplied by
iTerm2; it never updates whichever terminal happens to be active.

## Install and run

```bash
python3 -m pip install --user --no-deps .
python3 -m unittest discover -s tests -v
agent-terminal-bridge serve
agent-terminal-bridge doctor
```

Launch an agent through the bridge from iTerm2:

```bash
agent-terminal-bridge launch --agent codex -- codex
```

The bridge server is intentionally separate from agent startup. Start it in a
dedicated terminal, then launch a supported agent through the bridge:

```bash
agent-terminal-bridge launch --agent codex -- codex
```

The repository ships a Codex hook plugin manifest. Other adapters remain
manual until their native installer writes can be made as conservative and
reversible as the Codex path. `agent-terminal-bridge install --dry-run` does
not alter iTerm2 settings or trust hooks.

## Current support

| Agent | Normalized lifecycle mapping | Shipped registration |
| --- | --- | --- |
| Codex CLI | Yes | Codex plugin hook manifest |
| Claude Code | Yes | Manual hook setup pending |
| Cursor Agent | Yes | Manual hook setup pending |
| Kimi Code | Yes | Manual hook setup pending |
| Antigravity CLI | Yes | Manual hook setup pending |

This is deliberately not a claim that all five clients are installed or
equivalent yet. The published protocol and state machine are shared; agent
configuration publication is the remaining compatibility work.

## Privacy

The state service holds only session IDs, a launch nonce, agent name, project
basename, normalized state, timestamps, and active-child IDs in memory for its
process lifetime. It uses iTerm2's local `it2 session set-status` command and
has no network client, telemetry, or API key.

## License

MIT. This project is independently implemented; it does not include iTerm2's
Claude Code integration source.

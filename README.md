# Agent Terminal Bridge

Agent Terminal Bridge publishes privacy-safe lifecycle state to iTerm2's native
**Session Status** sidebar. It has normalized adapter definitions for Claude
Code, Codex CLI, Cursor Agent, Kimi Code, and Antigravity CLI.

It turns documented agent lifecycle events into iTerm2's three sidebar states:
`working`, `waiting`, and `idle`. Delivery health is reported separately as
`ready` or `unavailable`; on a delivery failure, iTerm retains its prior state.
It does not read prompts,
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

Install each non-Codex adapter only after reviewing its dry run. Each publisher
merges only its identifiable command entries, creates a verified neighboring
backup before a replacement, and never trusts a hook on your behalf:

```bash
agent-terminal-bridge install --agent claude --dry-run
agent-terminal-bridge install --agent claude
agent-terminal-bridge install --agent cursor
agent-terminal-bridge install --agent kimi
agent-terminal-bridge install --agent agy
```

Use each agent's native hook review UI after publication. The generic
`agent-terminal-bridge install --dry-run` does not alter iTerm2 settings or
trust hooks.

## Current support

| Agent | Normalized lifecycle mapping | Shipped registration |
| --- | --- | --- |
| Codex CLI | Yes | Codex plugin hook manifest |
| Claude Code | Yes | Opt-in user-settings publisher; native review still required |
| Cursor Agent | Yes | Opt-in user-hooks publisher |
| Kimi Code | Yes | Opt-in TOML hook publisher |
| Antigravity CLI | Yes | Opt-in global-hook publisher |

This is deliberately not a claim that all five clients are installed or
equivalent yet. Every publisher must still earn its adapter's native smoke
evidence; Cursor cloud sessions and undocumented upstream events remain outside
the local-status claim.

## Privacy

The state service holds only session IDs, a launch nonce, agent name, project
basename, normalized state, timestamps, and active-child IDs in memory for its
process lifetime. It uses iTerm2's local `it2 session set-status` command and
has no network client, telemetry, or API key.

## License

MIT. This project is independently implemented; it does not include iTerm2's
Claude Code integration source.

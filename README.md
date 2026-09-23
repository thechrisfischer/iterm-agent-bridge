# Agent Terminal Bridge

Agent Terminal Bridge is a local, privacy-safe lifecycle-event foundation for
an iTerm2 status and workgroup integration across Claude Code, Codex CLI,
Cursor Agent, Kimi Code, and Antigravity CLI.

It turns documented agent lifecycle events into four honest states:
`working`, `waiting`, `idle`, and `unavailable`. It does not read prompts,
terminal output, transcripts, command arguments, or credentials; it does not
approve, block, or otherwise affect agent actions.

## Development

```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests -v
agent-terminal-bridge serve
agent-terminal-bridge doctor
```

Launch an agent through the bridge from iTerm2:

```bash
agent-terminal-bridge launch --agent codex -- codex
```

The installer is opt-in. `agent-terminal-bridge install --dry-run` lists its
work and never enables iTerm2's Python API or trusts hooks.

## Privacy

The state service holds only session IDs, a launch nonce, agent name, project
basename, normalized state, timestamps, and active-child IDs in memory for its
process lifetime. It has no network client, telemetry, or API key.

## License

MIT. This project is independently implemented; it does not include iTerm2's
Claude Code integration source.

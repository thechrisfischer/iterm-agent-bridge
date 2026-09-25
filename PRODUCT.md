# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

delegated: a static HTML/CSS/JavaScript mock for this design exploration; runtime integration remains open

## Users

Inferred from the brief: developers and agent operators working in iTerm2 who need to scan several local repositories and monitor multiple coding-agent sessions without leaving the terminal context.

## Product Purpose

Agent Terminal Bridge publishes privacy-safe lifecycle state to iTerm2 and provides read-only review and background-agent panels. This mock explores a more useful review surface: a top-level workspace explorer that finds nested Git repositories, signals clean versus changed state, and opens a selected repository's diff beside a live agent activity view.

## Positioning

Inferred: the product sits inside the developer's terminal workflow and turns local repository and agent state into a compact, privacy-safe cockpit rather than a separate project-management dashboard.

## Operating Context

The user is in iTerm2, often with multiple agent sessions active at once. The surface must stay dark, dense, glanceable, and useful while work is changing in the background. Repository status is read-only. Agent state should include lifecycle state plus recent activity timing and useful mode context such as waiting, idle, or goal mode.

## Capabilities and Constraints

- Discover Git repositories below the currently navigated workspace root.
- Show all discovered repositories in a neutral state, highlighting repositories with uncommitted changes.
- Move focus through the repository list and open a selected repository's diff.
- Show background agent identity, project, lifecycle state, last-active time, and mode/context when available.
- Preserve the existing privacy boundary: no prompts, transcripts, tool arguments, or fabricated percent-complete values.
- This request is a concept mock; the data source, refresh mechanism, keyboard bindings, and exact iTerm rendering path remain open decisions.

## Brand Commitments

Existing product context is a dark terminal/iTerm2 environment with restrained state colors and monospace code/data where appropriate. The screenshot's charcoal surfaces and cool gray chrome are a binding reference for this exploration.

## Evidence on Hand

- Existing repository: `/Users/cfischer/Code/personal/iterm-agent-bridge`
- Existing review renderer: `src/agent_terminal_bridge/review.py`
- Existing cockpit layout creator: `src/agent_terminal_bridge/cockpit.py`
- Existing lifecycle terminology in README: `working`, `waiting`, `idle`, `ready`, and `unavailable`.
- No existing web UI, tokens, design system, or user-provided implementation screenshots beyond the attached iTerm2 screenshot.

## Product Principles

- Glance first: state should be readable before the user opens anything.
- Scope follows navigation: the current workspace root defines what is searched.
- Activity is temporal: last active time and current mode explain a state better than a static label.
- Read-only by default: the cockpit observes and explains; it does not intervene in agent work.
- Terminal-native density: useful information should fit beside the agent session without becoming a dashboard detached from the work.

## Accessibility & Inclusion

Inferred: status must not rely on color alone; icons, labels, and timestamps should reinforce state. Keyboard focus and readable contrast matter because the surface is intended for frequent, glance-based use.

# Timmy Tester: terminal review pane test plan

## Persona

Timmy is a keyboard-first developer who is impatient with invisible state.
He starts in a large workspace with dozens of repositories, expects the active
row to be unmistakable, and assumes Enter opens the thing currently selected.
He does not inspect logs or infer that a diff opened below the fold.

## Test fixture

- Run from a real iTerm2 session, not an embedded agent terminal.
- Use a workspace root containing at least 20 repositories.
- Include at least two clean repos and two dirty repos with different branches.
- Keep one dirty repo's diff large enough to scroll.
- Capture screenshots with Peekaboo after each checkpoint.

## Core journey

| ID | Timmy action | Expected result | Evidence |
| --- | --- | --- | --- |
| T1 | Run `aiterm review` | A new iTerm2 review-only pane opens; the agent pane remains intact. | `t1-open.png` |
| T2 | Press Down three times | The selection band and pointer move every time; the selected row stays visible. | `t2-navigation.png` |
| T3 | Land on a dirty repo and press Enter | The diff appears in the same viewport below the repo list. The diff header names the selected repo and branch. | `t3-open-diff.png` |
| T4 | Press `Ctrl-W`, Down | Focus changes to the diff and the footer confirms `focus: diff`. | `t4-diff-focus.png` |
| T5 | Press Down/PageDown in the diff | Diff content scrolls without changing the selected repository. | `t5-diff-scroll.png` |
| T6 | Press `Ctrl-W`, Up, then Up/Down | Focus returns to repos and navigation changes the highlighted row, not the diff scroll. | `t6-return-to-repos.png` |
| T7 | Press Enter on a clean repo | No diff opens; a clear clean-state message appears. | `t7-clean-repo.png` |
| T8 | Press `r` after changing a repo externally | Status and changed-file count refresh without losing the selected path. | `t8-refresh.png` |
| T9 | Run `agent-terminal-bridge review --watch` | Watcher runs in the current pane; this is intentionally different from `aiterm review`. | `t9-explicit-current-pane.png` |
| T10 | Run `aiterm review` outside iTerm2 | It exits with a clear “must be run from an iTerm2 session” error; it must not loop redraw text. | `t10-no-iterm-error.txt` |

## Failure patterns to watch for

- Selection changes internally but no visible highlight moves.
- Enter changes focus but the diff is below the viewport.
- A large repository list hides the selected row instead of scrolling to it.
- Ctrl-W is swallowed, leaves the UI in a waiting state, or switches the wrong pane.
- A clean repo receives a stale diff from the previous selection.
- Refresh resets the selected repo to the first row.
- Non-TTY fallback redraws endlessly when the user expected a new iTerm pane.

## Exit criteria

Timmy passes when every core journey reaches the expected visible state without
reading terminal escape codes, guessing hidden focus, or using a mouse. The
final evidence set includes screenshots for T1–T8 and a captured error for T10.

## Run log: 2026-09-25

Timmy ran the core flow in a real iTerm2 review session rooted at `/Users/cfischer`:

- T2 passed: 20 Down presses moved the high-contrast selection to `growth-hacking` and kept it visible at the bottom of the list. Evidence: `/tmp/timmy-t2-navigation.png`.
- T3 passed after fixing untracked-only patches: Enter opened the selected repository's diff below the list, with the live header reporting `+325 −0` for the untracked HTML file. Evidence: `/tmp/timmy-t3-live-line-count.png`.
- T5 passed: PageDown scrolled the diff while keeping `growth-hacking` selected. Evidence: `/tmp/timmy-t5-diff-scroll.png`.
- T6 passed using the terminal control-byte equivalent of Ctrl-W plus Up: focus returned to repos while the diff remained open. Evidence: `/tmp/timmy-t6-return-to-repos.png`.
- T7 passed: selecting `goodword-warehouse` and opening it cleared the previous diff and showed the clean-state message. Evidence: `/tmp/timmy-t7-clean-repo-final.png`.
- The Peekaboo `press return` semantic did not reach this iTerm session, while `press enter` did; the application handles both `10`, `13`, and `curses.KEY_ENTER`. This is recorded as a harness/input-delivery discrepancy, not a UI failure.

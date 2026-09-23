"""Read-only Git review rendering for an agent workspace."""

import subprocess
from pathlib import Path


def _git(root, *args):
    try:
        result = subprocess.run(["git", "-C", str(root)] + list(args), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def render_review(root="."):
    root = Path(root).resolve()
    top = _git(root, "rev-parse", "--show-toplevel")
    if not top:
        return "Git review\n\nNo Git worktree at %s." % root
    root = Path(top)
    branch = _git(root, "branch", "--show-current") or "detached HEAD"
    status = _git(root, "status", "--short")
    stat = _git(root, "diff", "--stat")
    cached = _git(root, "diff", "--cached", "--stat")
    check = _git(root, "diff", "--check")
    lines = ["Git review · %s" % root.name, "Branch: %s" % branch, ""]
    lines.append("Changed files:" if status else "Changed files: clean")
    lines.extend(status.splitlines() or ["  (none)"])
    lines.extend(["", "Unstaged diff:"])
    lines.extend(stat.splitlines() or ["  (none)"])
    lines.extend(["", "Staged diff:"])
    lines.extend(cached.splitlines() or ["  (none)"])
    lines.extend(["", "Whitespace check:"])
    lines.extend(check.splitlines() or ["  clean"])
    return "\n".join(lines)


def render_patch(root="."):
    root = Path(root).resolve()
    top = _git(root, "rev-parse", "--show-toplevel")
    if not top:
        return "No Git worktree at %s." % root
    patch = _git(top, "diff", "--no-ext-diff")
    return patch or "No unstaged diff."

"""Read-only Git review rendering and the interactive iTerm review pane."""

import curses
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


_SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__"}


def _git(root, *args):
    try:
        result = subprocess.run(["git", "-C", str(root)] + list(args), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


@dataclass(frozen=True)
class RepoStatus:
    path: Path
    branch: str
    changed_files: tuple
    additions: int = 0
    deletions: int = 0

    @property
    def dirty(self):
        return bool(self.changed_files)


def _status_paths(repo):
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=normal")
    paths = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1]
        paths.append((line[:2], path))
    return tuple(paths)


def _numstat(repo):
    additions = deletions = 0
    for line in _git(repo, "diff", "HEAD", "--numstat").splitlines():
        fields = line.split("\t")
        if len(fields) != 3:
            continue
        try:
            additions += int(fields[0])
            deletions += int(fields[1])
        except ValueError:
            # Binary diffs report '-' instead of a line count.
            continue
    for code, relative_path in _status_paths(repo):
        if code != "??":
            continue
        path = Path(repo) / relative_path
        if not path.is_file():
            continue
        try:
            additions += len(path.read_bytes().splitlines())
        except OSError:
            continue
    return additions, deletions


def repo_status(repo):
    repo = Path(repo).resolve()
    additions, deletions = _numstat(repo)
    return RepoStatus(
        path=repo,
        branch=_git(repo, "branch", "--show-current") or "detached HEAD",
        changed_files=_status_paths(repo),
        additions=additions,
        deletions=deletions,
    )


def _is_git_root(path):
    return (path / ".git").is_dir() or (path / ".git").is_file()


def discover_repositories(root="."):
    """Find Git repositories below ``root`` without descending into one twice."""
    root = Path(root).resolve()
    top = _git(root, "rev-parse", "--show-toplevel")
    if top:
        return (repo_status(Path(top)),)

    found = []
    if not root.exists() or not root.is_dir():
        return ()
    for current, directories, _files in os.walk(root):
        current_path = Path(current)
        directories[:] = [name for name in directories if name not in _SKIP_DIRS and not name.startswith(".")]
        if _is_git_root(current_path):
            found.append(repo_status(current_path))
            directories[:] = []
    return tuple(sorted(found, key=lambda repo: str(repo.path).lower()))


def _scope_name(root, repos):
    root = Path(root).resolve()
    if repos and len(repos) == 1 and repos[0].path == root:
        return root.name
    return root.name or str(root)


def render_review(root="."):
    """Render a compact non-interactive tree for pipes and non-TTY callers."""
    root = Path(root).resolve()
    repos = discover_repositories(root)
    if not repos:
        return "Git review\n\nNo Git worktree at %s." % root
    lines = ["Git review · %s" % _scope_name(root, repos), "", "▾ %s/ · %d repos" % (root.name, len(repos))]
    for repo in repos:
        marker = "●" if repo.dirty else "○"
        state = "%d changed" % len(repo.changed_files) if repo.dirty else "clean"
        lines.append("  %s %-32s %-18s %s" % (marker, repo.path.name, repo.branch, state))
    return "\n".join(lines)


def render_repo_patch(repo):
    """Return tracked and untracked changes as one reviewable patch."""
    pieces = []
    unstaged = _git(repo, "diff", "--no-ext-diff")
    staged = _git(repo, "diff", "--cached", "--no-ext-diff")
    if unstaged:
        pieces.append(unstaged)
    if staged:
        pieces.append(staged)
    for code, relative_path in _status_paths(repo):
        if code != "??":
            continue
        path = Path(repo) / relative_path
        if not path.is_file():
            continue
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), "diff", "--no-index", "--no-ext-diff", "/dev/null", str(path)],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=2, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.stdout:
            pieces.append(result.stdout.strip())
    return "\n".join(pieces)


def render_patch(root="."):
    root = Path(root).resolve()
    top = _git(root, "rev-parse", "--show-toplevel")
    if not top:
        return "No Git worktree at %s." % root
    patch = render_repo_patch(Path(top))
    return patch or "No unstaged diff."


class _ReviewUI:
    """Small terminal navigator kept deliberately close to the text pane."""

    def __init__(self, window, root, interval):
        self.window = window
        self.root = Path(root).resolve()
        self.interval = max(interval, .2)
        self.repos = ()
        self.selected = 0
        self.repo_scroll = 0
        self.focus = "repos"
        self.diff = []
        self.diff_scroll = 0
        self.prefix = False
        self.message = ""
        self.reload()

    def reload(self):
        old_path = self.repos[self.selected].path if self.repos and self.selected < len(self.repos) else None
        self.repos = discover_repositories(self.root)
        if old_path:
            self.selected = next((i for i, repo in enumerate(self.repos) if repo.path == old_path), 0)
        self.selected = min(self.selected, max(len(self.repos) - 1, 0))
        self.repo_scroll = min(self.repo_scroll, max(len(self.repos) - 1, 0))
        if self.diff and self.repos:
            self.open_diff(quiet=True)

    @property
    def selected_repo(self):
        return self.repos[self.selected] if self.repos else None

    def open_diff(self, quiet=False):
        repo = self.selected_repo
        if not repo:
            self.diff = []
            return
        if not repo.dirty:
            self.diff = []
            self.focus = "repos"
            self.message = "%s is clean — nothing to diff." % repo.path.name
            return
        self.diff = render_repo_patch(repo.path).splitlines()
        self.diff_scroll = 0
        self.focus = "diff"
        if not quiet:
            self.message = ""

    def move_focus(self, direction):
        if direction == "down" and self.diff:
            self.focus = "diff"
            self.message = ""
        elif direction == "up":
            self.focus = "repos"
            self.message = ""
        elif direction == "down":
            self.message = "Open a changed repository with Enter first."

    def handle(self, key):
        if self.prefix:
            self.prefix = False
            if key in (curses.KEY_DOWN, ord("j")):
                self.move_focus("down")
            elif key in (curses.KEY_UP, ord("k")):
                self.move_focus("up")
            else:
                self.message = "Ctrl-W is waiting for Up or Down."
            return True
        if key == 23:  # Ctrl-W, matching the familiar terminal window prefix.
            self.prefix = True
            self.message = "Ctrl-W … Up/Down to switch pane"
            return True
        if key in (ord("q"), 3):
            return False
        if key in (ord("r"), ord("R")):
            self.reload()
            self.message = "Scanned %d repositories." % len(self.repos)
            return True
        if key == curses.KEY_RESIZE:
            return True
        if key in (9,):  # Tab is a quick, discoverable alternate to Ctrl-W.
            self.focus = "diff" if self.focus == "repos" and self.diff else "repos"
            return True
        if self.focus == "repos":
            if key in (curses.KEY_DOWN, ord("j")) and self.repos:
                self.selected = min(len(self.repos) - 1, self.selected + 1)
            elif key in (curses.KEY_UP, ord("k")) and self.repos:
                self.selected = max(0, self.selected - 1)
            elif key in (curses.KEY_RIGHT, curses.KEY_ENTER, 10, 13):
                self.open_diff()
            return True
        if key in (curses.KEY_DOWN, ord("j")):
            self.diff_scroll = min(max(len(self.diff) - 1, 0), self.diff_scroll + 1)
        elif key in (curses.KEY_UP, ord("k")):
            self.diff_scroll = max(0, self.diff_scroll - 1)
        elif key in (curses.KEY_NPAGE,):
            self.diff_scroll += max(self.window.getmaxyx()[0] // 2, 1)
        elif key in (curses.KEY_PPAGE,):
            self.diff_scroll = max(0, self.diff_scroll - max(self.window.getmaxyx()[0] // 2, 1))
        return True

    @staticmethod
    def _add(window, row, col, text, attr=0, width=None):
        if row < 0 or col < 0:
            return
        if width is not None:
            text = text[:max(width, 0)]
        try:
            window.addstr(row, col, text, attr)
        except curses.error:
            pass

    def draw(self):
        window = self.window
        height, width = window.getmaxyx()
        window.erase()
        colors = self.colors
        self._add(window, 0, 0, "Git review", colors["head"])
        self._add(window, 0, 13, "· %s" % self.root, colors["muted"], width - 13)
        self._add(window, 1, 0, "▾ %s/ · %d repos" % (_scope_name(self.root, self.repos), len(self.repos)), colors["head"], width)
        self._add(window, 2, 0, "↑↓ move   Enter/→ open diff   Ctrl-W + ↑/↓ switch   Tab switch   r refresh   q quit", colors["quiet"], width)
        self._add(window, 3, 0, "─" * max(width, 1), colors["line"], width)

        list_start = 4
        reserved = 5 if self.diff else 2
        available = max(1, height - list_start - reserved)
        list_height = available
        if self.diff:
            list_height = max(6, available // 2)
            list_height = min(list_height, available)
        visible_count = max(1, list_height)
        if self.selected < self.repo_scroll:
            self.repo_scroll = self.selected
        elif self.selected >= self.repo_scroll + visible_count:
            self.repo_scroll = self.selected - visible_count + 1
        self.repo_scroll = min(self.repo_scroll, max(len(self.repos) - visible_count, 0))
        visible_repos = self.repos[self.repo_scroll:self.repo_scroll + visible_count]
        for offset, repo in enumerate(visible_repos):
            actual_index = self.repo_scroll + offset
            row = list_start + offset
            selected = actual_index == self.selected
            base = colors["selected"] | curses.A_BOLD if selected else 0
            marker = "●" if repo.dirty else "○"
            marker_attr = base if selected else (colors["dirty"] if repo.dirty else colors["clean"])
            self._add(window, row, 0, " " * width, base, width)
            self._add(window, row, 0, "▶" if selected else " ", base if selected else colors["head"])
            self._add(window, row, 1, marker, marker_attr | base)
            name_attr = base if selected else (colors["dirty"] if repo.dirty else colors["text"])
            self._add(window, row, 4, repo.path.name, name_attr, max(width - 4, 0))
            branch_col = max(5, width - len(repo.branch) - 18)
            self._add(window, row, branch_col, repo.branch, base if selected else colors["muted"], max(width - branch_col, 0))
            state = "%d changed" % len(repo.changed_files) if repo.dirty else "clean"
            state_col = max(branch_col + len(repo.branch) + 2, width - len(state) - 2)
            state_attr = base if selected else (colors["dirty"] if repo.dirty else colors["clean"])
            self._add(window, row, state_col, state, state_attr, max(width - state_col, 0))

        if not self.repos:
            self._add(window, list_start, 0, "No Git repositories under this path.", colors["muted"], width)

        if self.diff:
            divider_row = min(height - 2, list_start + visible_count)
            self._add(window, divider_row, 0, "─" * max(width, 1), colors["line"], width)
            repo = self.selected_repo
            self._add(window, divider_row + 1, 0, "%s · %s" % (repo.path.name, repo.branch), colors["head"], width)
            self._add(window, divider_row + 1, max(width - 18, 0), "+%d −%d" % (repo.additions, repo.deletions), colors["dirty"], width - max(width - 18, 0))
            diff_start = divider_row + 2
            visible = max(height - diff_start - 1, 0)
            for line_number, line in enumerate(self.diff[self.diff_scroll:self.diff_scroll + visible]):
                attr = colors["text"]
                if line.startswith("+") and not line.startswith("+++"):
                    attr = colors["add"]
                elif line.startswith("-") and not line.startswith("---"):
                    attr = colors["del"]
                self._add(window, diff_start + line_number, 0, line, attr, width)
        elif self.message:
            self._add(window, max(height - 2, 0), 0, self.message, colors["muted"], width)

        footer = "focus: %s" % self.focus
        if self.prefix:
            footer += " · Ctrl-W waiting"
        self._add(window, max(height - 1, 0), 0, footer, colors["quiet"], width)
        window.refresh()

    @property
    def colors(self):
        return self._colors

    def run(self):
        window = self.window
        window.keypad(True)
        try:
            curses.set_escdelay(1000)
        except AttributeError:
            pass
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        window.timeout(int(self.interval * 1000))
        self._colors = _init_colors()
        while True:
            self.draw()
            key = self._read_key()
            if key == -1:
                self.reload()
                continue
            if not self.handle(key):
                return 0

    def _read_key(self):
        """Normalize arrow escape sequences for terminals that split them."""
        key = self.window.getch()
        if key != 27:
            return key
        bracket = self.window.getch()
        if bracket != ord("["):
            return key
        final = self.window.getch()
        return {
            ord("A"): curses.KEY_UP,
            ord("B"): curses.KEY_DOWN,
            ord("C"): curses.KEY_RIGHT,
            ord("D"): curses.KEY_LEFT,
        }.get(final, key)


def _init_colors():
    if not curses.has_colors():
        return {name: 0 for name in ("head", "muted", "quiet", "line", "text", "selected", "dirty", "clean", "add", "del")}
    curses.start_color()
    curses.use_default_colors()
    pairs = {
        "head": (curses.COLOR_WHITE, -1),
        "muted": (curses.COLOR_CYAN, -1),
        "quiet": (curses.COLOR_WHITE, -1),
        "line": (curses.COLOR_BLUE, -1),
        "text": (curses.COLOR_WHITE, -1),
        "selected": (curses.COLOR_BLACK, curses.COLOR_CYAN),
        "dirty": (curses.COLOR_YELLOW, -1),
        "clean": (curses.COLOR_GREEN, -1),
        "add": (curses.COLOR_GREEN, -1),
        "del": (curses.COLOR_RED, -1),
    }
    colors = {}
    for index, (name, (foreground, background)) in enumerate(pairs.items(), 1):
        curses.init_pair(index, foreground, background)
        colors[name] = curses.color_pair(index)
    return colors


def run_review_ui(root=".", interval=2):
    """Run the interactive review pane until the user presses ``q``."""
    return curses.wrapper(lambda window: _ReviewUI(window, root, interval).run())

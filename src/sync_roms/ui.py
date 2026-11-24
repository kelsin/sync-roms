"""Terminal colors, prompts and progress output."""
import collections
import contextlib
import functools
import json
import os
import queue
import re
import shutil
import sys
import threading
import time
import unicodedata
from concurrent.futures import TimeoutError as FutureTimeout

from . import runtime


SPEED_WINDOW = 5  # seconds the current speed is averaged over
ETA_WINDOW = 60  # seconds the time left is averaged over
ETA_MIN = 5  # seconds of progress before a time left is shown
BACKLOG = 64 * 1024 * 1024  # bytes received but not yet written before the disk counts as the bottleneck
POLL = 0.25  # seconds between redraws of the progress bar while waiting on a job
PLAIN_INTERVAL = 30  # seconds between progress lines when stdout is not a terminal
ASSUME_YES = False  # --yes: prompts take their default answer (a default-no prompt stays no)
QUIET = False  # --quiet: stdout is discarded except emit_json(); prompts are asked on stderr
VERBOSE = False  # --verbose: debug() lines go to stderr
_real_stdout = None  # the stdout that --quiet replaced


def _use_color(stream):
    env = os.environ
    if "NO_COLOR" in env or env.get("TERM") == "dumb":
        return False
    return bool(env.get("FORCE_COLOR") or env.get("CLICOLOR_FORCE")) or stream.isatty()


_COLOR = _use_color(sys.stdout)


def c(code, text):
    color = _use_color(sys.stderr) if QUIET else _COLOR  # under --quiet only what goes to stderr is seen
    return f"\033[{code}m{text}\033[0m" if color else text


def err_color(code, text):
    """Like c(), but decided by stderr, for text that goes there."""
    return f"\033[{code}m{text}\033[0m" if _use_color(sys.stderr) else text


_thread = threading.local()


@contextlib.contextmanager
def silent_thread():
    """warn() and fail() print nothing on this thread inside the block (a background worker must not write over a
    list screen); fail() still raises."""
    before = getattr(_thread, "silent", False)
    _thread.silent = True
    try:
        yield
    finally:
        _thread.silent = before


def warn(text):
    if getattr(_thread, "silent", False):
        return
    print(err_color("33", f"⚠️  {text}"), file=sys.stderr)


def fail(text, code=3):
    """Exit with an error on stderr: code 3 for config/credential/tool problems, 2 for usage, 1 for failures."""
    if not getattr(_thread, "silent", False):
        print(err_color("31", f"❌ {text}"), file=sys.stderr)
    raise SystemExit(code)


_PLAIN_WORDS = {"✅": "ok", "❌": "failed", "⚠": "warning:"}
_EMOJI = re.compile("[\U0001F000-\U0001FFFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]+ *")


def plain(text):
    """text without emoji, for output that isn't a terminal (✅/❌/⚠️ become ok/failed/warning:)."""
    for emoji, word in _PLAIN_WORDS.items():
        text = re.sub(f"{emoji}\uFE0F? *", word + " ", text)
    return _EMOJI.sub("", text)


class PlainOut:
    """Wraps a non-terminal stdout so everything printed through it comes out without emoji."""
    def __init__(self, stream):
        self._stream = stream

    def write(self, text):
        return self._stream.write(plain(text))

    def __getattr__(self, name):
        return getattr(self._stream, name)


def table(rows, header=None):
    """Print rows (tuples of strings) in left-aligned columns sized to the longest cell; the last column isn't padded.
    header, if given, is printed bold."""
    allrows = ([header] if header else []) + [tuple(r) for r in rows]
    if not allrows:
        return
    widths = [max(cell_width(str(r[i])) for r in allrows) for i in range(len(allrows[0]))]
    for n, r in enumerate(allrows):
        cells = [str(v) + " " * (w - cell_width(str(v))) for v, w in zip(r, widths)]
        cells[-1] = cells[-1].rstrip()
        line = "  ".join(cells)
        print(bold(line) if header and n == 0 else line)


def bold(t): return c("1", t)
def dim(t): return c("2", t)
def red(t): return c("31", t)
def green(t): return c("32", t)
def yellow(t): return c("33", t)
def cyan(t): return c("36", t)


class _Discard:
    def write(self, text):
        return len(text)

    def flush(self):
        pass

    def isatty(self):
        return False


def set_output(quiet, verbose):
    """Apply --quiet and --verbose. reset() undoes it."""
    global QUIET, VERBOSE, _real_stdout
    QUIET, VERBOSE = quiet, verbose
    if quiet and _real_stdout is None:
        _real_stdout, sys.stdout = sys.stdout, _Discard()


def reset():
    global QUIET, VERBOSE, _real_stdout
    if _real_stdout is not None:
        sys.stdout = _real_stdout
    QUIET = VERBOSE = False
    _real_stdout = None


def emit_json(data):
    """Print data as JSON on stdout, even under --quiet."""
    (_real_stdout or sys.stdout).write(json.dumps(data, indent=2) + "\n")


def failure(text):
    """Print a line about something that failed: on stdout, or on stderr under --quiet (which discards stdout)."""
    print(text, file=sys.stderr if QUIET else sys.stdout)


def debug(text):
    if VERBOSE:
        print(dim(text), file=sys.stderr)


terminal_runner = None  # set during an editor session (picker.one_app): runs fn on the normal screen, outside the list app
prompter = None  # set during an editor session: prompter(question, keys) asks in the list app, or gives NOT_ASKED off its worker
NOT_ASKED = object()


def uses_terminal(fn):
    """fn uses the terminal (asks, or runs a command that may print or ask): during an editor session it runs through
    terminal_runner."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        return terminal_runner(fn, *args, **kwargs) if terminal_runner else fn(*args, **kwargs)
    return run


def in_app(spec):
    """fn asks a question: during an editor session its worker asks it in the list app instead (prompter), worded as
    spec(*fn's args) -> (question, keys) says; keys maps keys to answers (None: a line of text). spec gives None for
    a question that isn't asked (--yes)."""
    def wrap(fn):
        @functools.wraps(fn)
        def run(*args, **kwargs):
            if prompter and (asked := spec(*args, **kwargs)):
                got = prompter(*asked)
                if got is not NOT_ASKED:
                    return got
            return fn(*args, **kwargs)
        return run
    return wrap


def _input(prompt):
    if QUIET:  # stdout is discarded, so the question goes where a person (or log) can still see it
        sys.stderr.write(prompt)
        sys.stderr.flush()
        return input()
    return input(prompt)


@in_app(lambda prompt, cancellable=False: (prompt, None, cancellable))
@uses_terminal
def ask(prompt, cancellable=False):
    """input() that gives "" at end of input instead of raising, so a prompt with an empty answer means cancel. With
    cancellable, end of input (and Esc or ^G in the list app) gives None instead, so an empty line stays an answer."""
    try:
        return _input(prompt)
    except EOFError:
        print()
        return None if cancellable else ""


def _confirm_keys(question, default=True):
    """confirm's question in the list app: y/n, Enter the default, Esc or ^G no."""
    if not ASSUME_YES:
        return (f"{question} {'[Y/n]' if default else '[y/N]'} ",
                {"y": True, "n": False, "enter": default, "escape": False, "ctrl+g": False})


@in_app(_confirm_keys)
@uses_terminal
def confirm(question, default=True):
    suffix = "[Y/n]" if default else "[y/N]"
    if ASSUME_YES:
        print(f"{question} {suffix} {'y' if default else 'n'} (--yes)")
        return default
    while True:
        try:
            a = _input(f"{question} {suffix} ").strip().lower()
        except EOFError:  # no terminal to answer on: take the default
            print()
            return default
        if not a:
            return default
        if a in ("y", "yes"):
            return True
        if a in ("n", "no"):
            return False


def has_terminal():
    """Whether there is an interactive terminal to ask on."""
    return sys.stdin.isatty() and (_real_stdout or sys.stdout).isatty()  # --quiet swaps stdout for a discard sink


def require_terminal(what, flag):
    """Fail with the flag to use when a step needs an interactive terminal and there isn't one."""
    if not has_terminal():
        fail(f"Can't {what} without a terminal: pass {flag}", 2)


def _choose_keys(question, letters, default, legend=""):
    """choose's question in the list app: one of letters, Enter the default."""
    if not ASSUME_YES:
        suffix = "/".join(l.upper() if l == default else l for l in letters)
        return (f"{question} [{suffix}]{' (' + legend + ')' if legend else ''} ",
                {**dict(zip(letters, letters)), "enter": default})


@in_app(_choose_keys)
@uses_terminal
def choose(question, letters, default, legend=""):
    """Ask for one of `letters` (a string of single characters); Enter, --yes and EOF give `default`."""
    suffix = "/".join(l.upper() if l == default else l for l in letters)
    if ASSUME_YES:
        print(f"{question} [{suffix}] {default} (--yes)")
        return default
    while True:
        try:
            a = _input(f"{question} [{suffix}]{' (' + legend + ')' if legend else ''} ").strip().lower()
        except EOFError:
            print()
            return default
        if not a:
            return default
        if a[0] in letters:
            return a[0]


def choose_required(question, letters):
    """Ask for one of `letters` (single characters) with no default: Enter re-asks, and end of input stops (exit 2)
    rather than answering for the user. --yes doesn't apply."""
    suffix = "/".join(letters)
    while True:
        try:
            a = _input(f"{question} [{suffix}] ").strip().lower()
        except EOFError:
            print()
            fail("No answer to give (no terminal input); nothing was saved.", 2)
        if a and a[0] in letters:
            return a[0]


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def eta(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m" if seconds >= 3600 else f"{seconds // 60}m{seconds % 60:02d}s"


class ProgressBar:
    """One line under the log, then a line per file in flight: say() prints a line above it, draw() refreshes it. Does nothing but print on a non-tty."""
    def __init__(self, count, fraction, total_bytes=None, io=None, active=None):
        self.active = active  # () -> [(name, moved, size)] of the files in flight, shown under the bar
        self.io = io  # a ByteProgress that also counts bytes written, to tell a slow network from a slow disk
        self.count, self.fraction = count, fraction  # fraction() is the 0-1 progress of the whole run
        self.of = f" of {human_size(total_bytes)}" if total_bytes else ""  # the bar is by size, the count is by file
        self.shown = sys.stdout.isatty()
        self.total = total_bytes or 0
        self.started = time.monotonic()
        self.last_line = self.started
        self.samples = collections.deque()  # (time, bytes moved, bytes written) over the last ETA_WINDOW seconds

    def say(self, line):
        print(("\r\033[J" if self.shown else "") + line)  # \033[J also wipes the block under the bar

    def draw(self, done):
        if not self.shown:  # no terminal to redraw on: a plain line every PLAIN_INTERVAL seconds
            now = time.monotonic()
            if now - self.last_line >= PLAIN_INTERVAL:
                self.last_line = now
                print(f"progress: {done}/{self.count} files done, {self.fraction():.0%}{self.of}")
        if self.shown:
            fraction = self.fraction()
            filled = int(fraction * 24)
            now = time.monotonic()
            self.samples.append((now, self.total * fraction, self.io.written if self.io else 0))
            while len(self.samples) > 1 and now - self.samples[0][0] > ETA_WINDOW:
                self.samples.popleft()
            tiers = [""]  # speed text, fullest first; the line drops detail until it fits the terminal
            recent = next(s for s in self.samples if now - s[0] <= SPEED_WINDOW)  # the newest sample always qualifies
            span = now - recent[0]
            if self.total and span >= 1:
                rate = (self.samples[-1][1] - recent[1]) / span  # current speed, not the run's average
                long_span = now - self.samples[0][0]
                long_rate = (self.samples[-1][1] - self.samples[0][1]) / long_span  # steadier, for the time left
                left = f", {eta(self.total * (1 - fraction) / long_rate)} left" if long_span >= ETA_MIN and long_rate > 0 else ""
                tiers = [f"  {human_size(rate)}/s{left}"]
                if self.io and self.io.written:
                    disk = (self.samples[-1][2] - recent[2]) / span
                    net = f"  net {human_size(rate)}/s · disk {human_size(disk)}/s{left}"
                    waiting = " · waiting on " + ("disk" if self.io.received - self.io.written > BACKLOG else "network")
                    tiers = [net + waiting, net] + tiers
            head = f"{done}/{self.count} files done  {fraction:4.0%}{self.of}"
            room = shutil.get_terminal_size().columns - 1 - 2 - 24 - 1 - len(head)  # one column spare so the line never wraps
            speed = next((t for t in tiers if len(t) <= room), "")
            sys.stdout.write(f"\r\033[J  {cyan('█' * filled)}{dim('░' * (24 - filled))} {head}{speed}")
            block = self.block()
            for line in block:
                sys.stdout.write("\n" + line)
            if block:
                sys.stdout.write(f"\033[{len(block)}A\r")  # back on the bar line
            sys.stdout.flush()

    def block(self):
        """The lines under the bar, colored and none wider than the terminal: a file each, or fewer and "… and N more" when the terminal is short."""
        active = self.active() if self.active else []
        size = shutil.get_terminal_size()
        room, width = size.lines - 2, size.columns - 1
        if room <= 0 or not active:
            return []
        shown = active if len(active) <= room else active[:room - 1]
        lines = []
        for name, moved, total in shown:
            filled = int(moved / total * 10)
            tail = f"  {moved / total:4.0%} of {human_size(total)}"
            fit = width - cell_width("    ↓ ") - 11 - cell_width(tail)  # 11: the file's bar and a space
            if cell_width(name) > fit:
                name = cut_cells(name, max(0, fit - 1)) + "…"
            line = cut_cells(f"    ↓ {'█' * filled}{'░' * (10 - filled)} {name}{tail}", width)  # cut plain, then colored
            lines.append(dim(line[:6]) + cyan(line[6:6 + filled]) + dim(line[6 + filled:]))
        if len(shown) < len(active):
            lines.append(dim(f"    … and {len(active) - len(shown)} more"))
        return lines

    def clear(self):
        if self.shown:
            sys.stdout.write("\r\033[J")
            sys.stdout.flush()


def cell_width(text):
    """Terminal cells text takes up (emoji and CJK are two wide)."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def cut_cells(text, width):
    """The start of text that fits in width cells (a wide character is never split)."""
    used = 0
    for n, c in enumerate(text):
        used += cell_width(c)
        if used > width:
            return text[:n]
    return text


def wait_drawing(bar, done, get):
    """get(timeout=...) once it returns (a future's result, a queue's get), redrawing the bar with `done` files done while waiting."""
    while True:
        try:
            return get(timeout=POLL)
        except (FutureTimeout, queue.Empty):
            bar.draw(done)


class ByteProgress:
    """Bytes moved per job (weighted by size, at least 1 so empty files count); fraction() is the overall 0-1."""
    def __init__(self, sizes):
        self.size = [max(1, s or 0) for s in sizes]
        self.moved = [0] * len(sizes)
        self.total, self.done = sum(self.size), 0  # bytes in all jobs, and moved so far (kept as a running sum)
        self.received = self.written = 0  # totals across all jobs; written stays 0 unless the job reports it
        self.lock = threading.Lock()
        self.started, self.finished = {}, set()  # in flight (job -> None, in start order), and done for good

    def start(self, i):
        with self.lock:
            if i not in self.finished:
                self.started.setdefault(i, None)

    def active(self, names):
        """(name, moved, size) of each job in flight, oldest start first."""
        with self.lock:
            return [(names[i], self.moved[i], self.size[i]) for i in self.started]

    def add(self, i, n):
        with self.lock:
            if i not in self.finished:
                self.started.setdefault(i, None)  # uploads have no start hook: first bytes are the start
            step = min(self.size[i] - self.moved[i], n)
            self.moved[i] += step
            self.done += step
            self.received += n

    def wrote(self, n):
        with self.lock:
            self.written += n

    def finish(self, i):
        with self.lock:
            self.done += self.size[i] - self.moved[i]
            self.moved[i] = self.size[i]
            self.started.pop(i, None)
            self.finished.add(i)

    def fraction(self):
        return self.done / self.total


def print_head(items, n, fmt=str, indent=7, paint=dim):
    """Print the first n items, one per line, then "… and M more" when there are others: dimmed, 7 spaces in, unless
    paint and indent say otherwise."""
    for item in items[:n]:
        print(paint(f"{' ' * indent}{fmt(item)}"))
    if len(items) > n:
        print(paint(f"{' ' * indent}… and {len(items) - n} more"))


def report_missing(keys, what):
    if not keys:
        return
    from . import inventory  # imported here: inventory imports this module
    print(yellow(f"  ⚠️  {len(keys)} {what} listed in manifest but not in storage"))
    print_head(keys, runtime.MAX_MISSING_SHOWN)
    if inventory.current() is not None:
        print(dim(f"     Added to storage since the cache was built? Run: {inventory.UPDATE_HINT}"))

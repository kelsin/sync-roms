"""Terminal colors, prompts and progress output."""
import json
import os
import re
import sys
import threading
import time

from . import runtime


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
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def err_color(code, text):
    """Like c(), but decided by stderr, for text that goes there."""
    return f"\033[{code}m{text}\033[0m" if _use_color(sys.stderr) else text


def warn(text):
    print(err_color("33", f"⚠️  {text}"), file=sys.stderr)


def fail(text, code=3):
    """Exit with an error on stderr: code 3 for config/credential/tool problems, 2 for usage, 1 for failures."""
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


def debug(text):
    if VERBOSE:
        print(dim(text), file=sys.stderr)


def _input(prompt):
    if QUIET:  # stdout is discarded, so the question goes where a person (or log) can still see it
        sys.stderr.write(prompt)
        sys.stderr.flush()
        return input()
    return input(prompt)


def ask(prompt):
    """input() that gives "" at end of input instead of raising, so a prompt with an empty answer means cancel."""
    try:
        return _input(prompt)
    except EOFError:
        print()
        return ""


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


def require_terminal(what, flag):
    """Fail with the flag to use when a step needs an interactive terminal and there isn't one."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        fail(f"Can't {what} without a terminal: pass {flag}", 2)


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
    """One line under the log: say() prints a line above it, draw() refreshes it. Does nothing but print on a non-tty."""
    def __init__(self, count, fraction, total_bytes=None):
        self.count, self.fraction = count, fraction  # fraction() is the 0-1 progress of the whole run
        self.of = f" of {human_size(total_bytes)}" if total_bytes else ""  # the bar is by size, the count is by file
        self.shown = sys.stdout.isatty()
        self.total = total_bytes or 0
        self.started = time.monotonic()
        self.last_line = self.started

    def say(self, line):
        print(("\r\033[K" if self.shown else "") + line)

    def draw(self, done):
        if not self.shown:  # no terminal to redraw on: a plain line every PLAIN_INTERVAL seconds
            now = time.monotonic()
            if now - self.last_line >= PLAIN_INTERVAL:
                self.last_line = now
                print(f"progress: {done}/{self.count} files done, {self.fraction():.0%}{self.of}")
        if self.shown:
            fraction = self.fraction()
            filled = int(fraction * 24)
            elapsed = time.monotonic() - self.started
            speed = ""
            if self.total and fraction > 0.01 and elapsed > 2:
                speed = f"  {human_size(self.total * fraction / elapsed)}/s, {eta(elapsed * (1 - fraction) / fraction)} left"
            sys.stdout.write(f"\r\033[K  {cyan('█' * filled)}{dim('░' * (24 - filled))} {done}/{self.count} files done  {fraction:4.0%}{self.of}{speed}")
            sys.stdout.flush()

    def clear(self):
        if self.shown:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()


class ByteProgress:
    """Bytes moved per job (weighted by size, at least 1 so empty files count); fraction() is the overall 0-1."""
    def __init__(self, sizes):
        self.size = [max(1, s or 0) for s in sizes]
        self.moved = [0] * len(sizes)
        self.lock = threading.Lock()

    def add(self, i, n):
        with self.lock:
            self.moved[i] = min(self.size[i], self.moved[i] + n)

    def finish(self, i):
        with self.lock:
            self.moved[i] = self.size[i]

    def fraction(self):
        return sum(self.moved) / sum(self.size)


def report_missing(keys, what):
    if not keys:
        return
    print(yellow(f"  ⚠️  {len(keys)} {what} listed in manifest but not in bucket"))
    for k in keys[:runtime.MAX_MISSING_SHOWN]:
        print(dim(f"       {k}"))
    if len(keys) > runtime.MAX_MISSING_SHOWN:
        print(dim(f"       … and {len(keys) - runtime.MAX_MISSING_SHOWN} more"))

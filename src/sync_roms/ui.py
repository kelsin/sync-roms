"""Terminal colors, prompts and progress output."""
import os
import sys
import threading

from . import runtime


_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ


def c(code, text):
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def bold(t): return c("1", t)
def dim(t): return c("2", t)
def red(t): return c("31", t)
def green(t): return c("32", t)
def yellow(t): return c("33", t)
def cyan(t): return c("36", t)


def confirm(question, default=True):
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        a = input(f"{question} {suffix} ").strip().lower()
        if not a:
            return default
        if a in ("y", "yes"):
            return True
        if a in ("n", "no"):
            return False


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class ProgressBar:
    """One line under the log: say() prints a line above it, draw() refreshes it. Does nothing but print on a non-tty."""
    def __init__(self, count, fraction, total_bytes=None):
        self.count, self.fraction = count, fraction  # fraction() is the 0-1 progress of the whole run
        self.of = f" of {human_size(total_bytes)}" if total_bytes else ""  # the bar is by size, the count is by file
        self.shown = sys.stdout.isatty()

    def say(self, line):
        print(("\r\033[K" if self.shown else "") + line)

    def draw(self, done):
        if self.shown:
            fraction = self.fraction()
            filled = int(fraction * 24)
            sys.stdout.write(f"\r\033[K  {cyan('█' * filled)}{dim('░' * (24 - filled))} {done}/{self.count} files done  {fraction:4.0%}{self.of}")
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

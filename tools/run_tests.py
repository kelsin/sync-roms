"""Runs the test suite in parallel processes: `uv run python tools/run_tests.py [-j N]`.

Slow modules are split into shards (`module@i/k`, one process each) and started first, then the modules that stay
one process each, then the rest, batched `BATCH` modules to a process. A process runs its units in one `unittest`
run, so `isolate` gives it one throwaway HOME (like the single-process `python -m unittest discover -s tests`); the
tests are the same ones. Output is shown only for failing processes."""
import argparse
import os
import re
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

TESTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests")
SHARDS = {"test_picker_session": 5, "test_custom_themes": 4, "test_theme_palettes": 3, "test_edit": 2}
SOLO = ["test_frames", "test_cardedit", "test_s3", "test_flash", "test_imports", "test_scrape_run"]
BATCH = 6


def modules():
    return sorted(f[:-3] for f in os.listdir(TESTS) if f.startswith("test_") and f.endswith(".py"))


def plan(names):
    """The processes to start, each a list of units (`module` or `module@i/k`), in start order."""
    shards = [[f"{m}@{i}/{SHARDS[m]}"] for m in names if m in SHARDS for i in range(SHARDS[m])]
    solo = [[m] for m in names if m in SOLO]
    rest = [m for m in names if m not in SHARDS and m not in SOLO]
    return shards + solo + [rest[i:i + BATCH] for i in range(0, len(rest), BATCH)]


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


def shard(tests, i, k):
    return tests[i::k]


def child(units):
    sys.path.insert(0, TESTS)
    tests = []
    for unit in units:
        name, _, part = unit.partition("@")
        found = list(flatten(unittest.defaultTestLoader.loadTestsFromName(name)))
        if part:
            i, k = map(int, part.split("/"))
            found = shard(found, i, k)
        tests += found
    return 0 if unittest.TextTestRunner().run(unittest.TestSuite(tests)).wasSuccessful() else 1


def run(units):
    start = time.time()
    p = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", *units],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True)
    return units, p.returncode, p.stdout + p.stderr, time.time() - start


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-j", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--child", nargs="+", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.child:
        return child(args.child)
    names = modules()
    procs = plan(names)
    failed = []
    count = 0
    start = time.time()
    with ThreadPoolExecutor(args.j) as pool:
        for units, code, output, took in pool.map(run, procs):
            count += sum(int(n) for n in re.findall(r"^Ran (\d+) tests?", output, re.M))
            if code:
                failed.append(" ".join(units))
                print(f"=== {' '.join(units)} FAILED ({took:.1f}s)\n{output}")
    print(f"{count} tests in {len(names)} modules ({len(procs)} processes) in {time.time() - start:.1f}s; "
          + (f"failed: {', '.join(failed)}" if failed else "all passed"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

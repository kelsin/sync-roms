"""Runs the test suite with one process per test module, in parallel: `uv run python tools/run_tests.py [-j N]`.

Each module is its own `unittest` run, so `isolate` gives each its own throwaway HOME; the tests are the same ones
`python -m unittest discover -s tests` runs. The slowest modules start first. Output is shown only for failing modules."""
import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

TESTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests")
SLOW_FIRST = ["test_custom_themes", "test_picker_session", "test_theme_palettes", "test_edit", "test_frames"]


def run(module):
    start = time.time()
    p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", TESTS, "-p", module + ".py"],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True)
    return module, p.returncode, p.stdout + p.stderr, time.time() - start


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-j", type=int, default=os.cpu_count() or 1)
    args = ap.parse_args()
    modules = sorted(f[:-3] for f in os.listdir(TESTS) if f.startswith("test_") and f.endswith(".py"))
    modules.sort(key=lambda m: SLOW_FIRST.index(m) if m in SLOW_FIRST else len(SLOW_FIRST))
    failed = []
    count = 0
    start = time.time()
    with ThreadPoolExecutor(args.j) as pool:
        for module, code, output, took in pool.map(run, modules):
            count += sum(int(n) for n in re.findall(r"^Ran (\d+) tests?", output, re.M))
            if code:
                failed.append(module)
                print(f"=== {module} FAILED ({took:.1f}s)\n{output}")
    print(f"{count} tests in {len(modules)} modules in {time.time() - start:.1f}s; "
          + (f"failed: {', '.join(failed)}" if failed else "all passed"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

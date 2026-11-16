# Live Transfer List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** While downloading or uploading, print each file's ✅/❌ line as soon as it finishes, not in queue order, and list the files currently in flight below the progress bar.

**Architecture:** `ui.ByteProgress` also tracks which jobs are in flight, in the order they started. `ui.ProgressBar` gets an optional `active` callable and draws one line per in-flight file under the bar, fitted to the terminal's height and width. `downloads.run_downloads` and `upload.run_copies` stop waiting on futures in submission order and handle them as they complete. `upload.run_uploads` already prints in completion order and only gains the in-flight block.

**Tech Stack:** Python ≥3.12 stdlib (`concurrent.futures`, ANSI escapes), `unittest`.

**Spec:** this plan. The request: "show (at the bottom of the list) what files are being currently downloaded and show files as they finish instead of waiting for them linearly"; upload paths get the same behavior; "show less when there isn't room".

## Global Constraints

- Run tests with `.venv/bin/python -m unittest discover -s tests` from the worktree root (`.venv` is Python 3.15.2; baseline: 1737 tests, OK).
- Conventional Commits, lowercase imperative (e.g. `feat(ui): ...`).
- Never mention Claude/AI in commits. No `Co-Authored-By` lines.
- Non-tty output (`bar.shown` False) is unchanged: no in-flight block, same periodic `progress:` lines.
- `chd.py`'s `ProgressBar` use is untouched and must render exactly as before (it passes no `active`).
- Bar line rendering (`head`, speed tiers, width fitting) is unchanged.

## Review Focus

1. Terminal shorter than the in-flight list: block shrinks to fit, with `… and N more` (Task 1 test).
2. Long names or narrow terminal: no block line wraps (Task 1 test).
3. Ctrl-C while the block is shown: the interrupt message and `bar.clear()` must not leave stale block lines (`say`/`clear` clear to end of screen; Task 1 test).
4. Many files finishing within one poll: each printed exactly once, counter ends at `[N/N]` (Task 2 and 3 tests).
5. A failing file: printed in completion order with ❌ and removed from the in-flight list (Task 2 test).

---

### Task 1: In-flight tracking and the block under the bar

**Files:**
- Modify: `src/sync_roms/ui.py` (`ProgressBar`, `ByteProgress`)
- Test: `tests/test_ui_progress.py`

**Interfaces:**
- Produces:
  - `ByteProgress.start(i: int) -> None`: marks job `i` in flight (no-op if already in flight or finished).
  - `ByteProgress.add(i, n)`: as today, and also marks `i` in flight unless it has finished (s3transfer uploads have no start hook; first bytes count as start).
  - `ByteProgress.finish(i)`: as today, and removes `i` from the in-flight set; a later `add(i, …)` must not put it back.
  - `ByteProgress.active(names: list[str]) -> list[tuple[str, int, int]]`: `(names[i], moved[i], size[i])` for each in-flight job, oldest start first. Thread-safe (take `self.lock`).
  - `ProgressBar(count, fraction, total_bytes=None, io=None, active=None)`: `active` is a zero-arg callable returning that list.

- [ ] **Step 1: Write the failing tests** in `tests/test_ui_progress.py`

```python
class ActiveTest(unittest.TestCase):
    def test_active_is_in_start_order_and_drops_finished_jobs(self):
        moved = ui.ByteProgress([10, 20, 30])
        moved.start(1)
        moved.add(0, 5)  # first bytes count as a start
        self.assertEqual(moved.active(["a", "b", "c"]), [("b", 0, 20), ("a", 5, 10)])
        moved.finish(1)
        moved.add(1, 3)  # a late callback doesn't bring it back
        moved.start(1)
        self.assertEqual(moved.active(["a", "b", "c"]), [("a", 5, 10)])


class BlockTest(unittest.TestCase):
    def draw(self, active, columns=80, rows=24):
        bar = ui.ProgressBar(len(active), lambda: 0.5, active=lambda: active)
        bar.shown = True
        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
                mock.patch.object(ui.shutil, "get_terminal_size", return_value=os.terminal_size((columns, rows))):
            bar.draw(0)
        return out.getvalue()

    def lines(self, text):
        return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text).replace("\r", "").split("\n")

    def test_lists_each_file_in_flight_below_the_bar_and_returns_to_it(self):
        out = self.draw([("gba/a.zip", 5, 10), ("gba/b.zip", 0, 2048)])
        below = self.lines(out)[1:]
        self.assertEqual(len(below), 2)
        self.assertIn("gba/a.zip", below[0])
        self.assertIn("50%", below[0])
        self.assertIn("gba/b.zip", below[1])
        self.assertIn("2.0 KB", below[1])
        self.assertTrue(out.endswith("\x1b[2A\r"))  # cursor back on the bar line

    def test_short_terminal_shows_fewer_files_and_counts_the_rest(self):
        out = self.draw([(f"gba/{n}.zip", 0, 1) for n in range(8)], rows=5)  # room for rows - 2 = 3 lines
        below = self.lines(out)[1:]
        self.assertEqual(len(below), 3)
        self.assertIn("gba/0.zip", below[0])
        self.assertIn("gba/1.zip", below[1])
        self.assertIn("… and 6 more", below[2])

    def test_no_room_shows_no_block(self):
        out = self.draw([("gba/a.zip", 0, 1)], rows=2)
        self.assertEqual(len(self.lines(out)), 1)
        self.assertNotIn("\x1b[", out.rsplit("░", 1)[-1].split("files done")[0])  # no cursor-up for an empty block

    def test_long_names_never_wrap(self):
        out = self.draw([("psx/" + "x" * 300 + ".chd", 0, 10 ** 9)], columns=40)
        for line in self.lines(out)[1:]:
            self.assertLessEqual(len(line), 39)
        self.assertIn("…", self.lines(out)[1])

    def test_no_active_draws_just_the_bar(self):
        out = self.draw([])
        self.assertEqual(len(self.lines(out)), 1)

    def test_say_and_clear_wipe_the_block_too(self):
        bar = ui.ProgressBar(1, lambda: 0)
        bar.shown = True
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            bar.say("x")
            bar.clear()
        self.assertEqual(out.getvalue(), "\r\x1b[Jx\n\r\x1b[J")

    def test_non_tty_never_prints_the_block(self):
        bar = ui.ProgressBar(1, lambda: 0, active=lambda: [("gba/a.zip", 0, 1)])
        bar.shown = False
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            bar.draw(0)
        self.assertNotIn("gba/a.zip", out.getvalue())
```

Add `import re` to the test file. If `test_no_room_shows_no_block`'s last assertion is awkward against the real output, replace it with `self.assertFalse(out.endswith("A\r"))`; the intent is: no block lines and no cursor-up.

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m unittest tests.test_ui_progress -v`
Expected: the new tests FAIL/ERROR (`start`/`active` missing, unexpected `active` kwarg); existing tests pass.

- [ ] **Step 3: Implement in `src/sync_roms/ui.py`**

- `ByteProgress`: keep a `dict` of in-flight index → start sequence (or an insertion-ordered dict) plus a `finished` set, all under `self.lock`.
- `ProgressBar.say` writes `"\r\033[J"` (not `\033[K`) before the line on a tty; `clear` writes `"\r\033[J"`. This wipes the block below the bar as well.
- `ProgressBar.draw` (tty branch): start with `"\r\033[J"`, write the bar line exactly as today, then the block:
  - `rows = shutil.get_terminal_size().lines`, `room = rows - 2`. If `room <= 0` or nothing active: no block.
  - If `len(active) <= room`: one line per file. Otherwise `room - 1` file lines, then `… and {len(active) - (room - 1)} more`.
  - File line (visible text, then wrapped in `dim()`): `f"    ↓ {name}  {moved / size:4.0%} of {human_size(size)}"`. Fit it to `columns - 1` visible characters by cutting the end of the name and adding `…`, keeping the percent and size; if even that doesn't fit, cut the whole line to `columns - 1`.
  - Each block line is written as `"\n" + line`; after the block, write `f"\033[{n}A\r"` (n = block lines) so the cursor sits at the start of the bar line.
- Use `↓` (single column), not an emoji.

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/ui.py tests/test_ui_progress.py
git commit -m "feat(ui): list in-flight transfers under the progress bar"
```

---

### Task 2: Downloads print as they finish and show what's in flight

**Files:**
- Modify: `src/sync_roms/downloads.py` (`run_downloads`)
- Modify: `README.md` (sync step 4, the "Each finished file prints as…" sentence)
- Test: `tests/test_sync_flow.py` (next to the `run_interrupted` tests)

**Interfaces:**
- Consumes: `ByteProgress.start/active/finish`, `ProgressBar(..., active=...)` from Task 1.

- [ ] **Step 1: Write the failing tests**

```python
class CompletionOrderTest(unittest.TestCase):
    def test_a_file_that_finishes_first_prints_first_while_a_slow_one_is_listed(self):
        jobs = [("gba/slow.zip", "/tmp/x/slow.zip", 5), ("gba/fast.zip", "/tmp/x/fast.zip", 5)]
        fast_printed, seen = threading.Event(), []
        real_say = ui.ProgressBar.say

        def say(self_, line):
            if "fast.zip" in line:
                seen.append([n for n, _, _ in self_.active()])
                fast_printed.set()
            real_say(self_, line)

        def download(job, callback=None, wrote=None):
            if "slow" in job[0]:
                assert fast_printed.wait(5)

        with mock.patch.object(s3, "download", download), mock.patch.object(ui.ProgressBar, "say", say), \
                mock.patch.object(ui, "POLL", 0.001):
            failed, out = captured(downloads.run_downloads, jobs, "ROMs", "i", "/tmp/x")
        self.assertEqual(failed, 0)
        lines = [l for l in out.splitlines() if "✅" in l]
        self.assertIn("[1/2]", lines[0]); self.assertIn("gba/fast.zip", lines[0])
        self.assertIn("[2/2]", lines[1]); self.assertIn("gba/slow.zip", lines[1])
        self.assertEqual(seen, [["gba/slow.zip"]])

    def test_many_instant_files_each_print_once(self):
        jobs = [(f"gba/{n}.zip", f"/tmp/x/{n}.zip", 1) for n in range(20)]
        with mock.patch.object(s3, "download", lambda *a, **k: None), mock.patch.object(ui, "POLL", 0.001):
            _, out = captured(downloads.run_downloads, jobs, "ROMs", "i", "/tmp/x")
        for n in range(20):
            self.assertEqual(out.count(f"gba/{n}.zip"), 1)
        self.assertIn("[20/20]", out)

    def test_a_failure_prints_when_it_happens(self):
        jobs = [("gba/slow.zip", "/tmp/x/slow.zip", 5), ("gba/bad.zip", "/tmp/x/bad.zip", 5)]
        bad_printed = threading.Event()
        real_say = ui.ProgressBar.say

        def say(self_, line):
            if "bad.zip" in line:
                bad_printed.set()
            real_say(self_, line)

        def download(job, callback=None, wrote=None):
            if "bad" in job[0]:
                raise OSError("boom")
            assert bad_printed.wait(5)

        with mock.patch.object(s3, "download", download), mock.patch.object(ui.ProgressBar, "say", say), \
                mock.patch.object(ui, "POLL", 0.001):
            failed, out = captured(downloads.run_downloads, jobs, "ROMs", "i", "/tmp/x")
        self.assertEqual(failed, 1)
        self.assertLess(out.index("bad.zip"), out.index("✅"))
```

Use the module's existing imports for `s3`, `ui`, `downloads`; add `import threading` if missing.

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m unittest tests.test_sync_flow.CompletionOrderTest -v`
Expected: FAIL (output in submission order; the first test hangs up to 5s and then fails).

- [ ] **Step 3: Implement in `run_downloads`**

- `names = [j[0] for j in todo]`; build the bar with `active=lambda: moved.active(names)`.
- Each worker calls `moved.start(i)` before `s3.download(...)` (a small wrapper submitted to the pool), so a file shows at 0% while it connects.
- Replace the in-order loop with `concurrent.futures.wait(pending, timeout=ui.POLL, return_when=FIRST_COMPLETED)`: on timeout, `bar.draw(finished)`; for each completed future, handle it in submission order within the batch, `finished += 1`, `prog = [finished/N]`, call `moved.finish(job_index)` (the job's own index, not the counter) on success and on failure, keep today's ✅/❌ text, `failures` append and `bar.draw(finished)`.
- Keep the `KeyboardInterrupt` branch and the `finally` as they are (they already work from the futures list).

- [ ] **Step 4: Update `README.md`** sync step 4: say each file prints as soon as it finishes (so `i` is the count finished so far), and that in a terminal the files downloading right now are listed under the progress bar (fewer when the terminal is short).

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add src/sync_roms/downloads.py tests/test_sync_flow.py README.md
git commit -m "feat(sync): print downloads as they finish and list the ones in flight"
```

---

### Task 3: Uploads and storage-folder copies get the same behavior

**Files:**
- Modify: `src/sync_roms/upload.py` (`run_copies`, `run_uploads`)
- Modify: `README.md` only if it describes upload output order (grep for `✅` near upload/scrape sections; no change if nothing describes it)
- Test: `tests/test_upload.py`

**Interfaces:**
- Consumes: `ByteProgress.start/active/finish`, `ProgressBar(..., active=...)` from Task 1.

- [ ] **Step 1: Write the failing tests** in `tests/test_upload.py`

```python
class CopyOrderTest(unittest.TestCase):
    def test_a_copy_that_finishes_first_prints_first_while_a_slow_one_is_listed(self):
        # sizes put big.zip first in the biggest-first order
        todo = [("gba/big.zip", "/src/big.zip", 100), ("gba/small.zip", "/src/small.zip", 1)]
        small_printed, seen = threading.Event(), []
        real_say = ui.ProgressBar.say

        def say(self_, line):
            if "small.zip" in line:
                seen.append([n for n, _, _ in self_.active()])
                small_printed.set()
            real_say(self_, line)

        def write_file(key, write):
            if "big" in key:
                assert small_printed.wait(5)

        with mock.patch.object(upload.s3, "write_file", write_file), mock.patch.object(ui.ProgressBar, "say", say), \
                mock.patch.object(ui, "POLL", 0.001):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                failed = upload.run_copies(todo)
        self.assertEqual(failed, 0)
        lines = [l for l in out.getvalue().splitlines() if "✅" in l]
        self.assertIn("[1/2]", lines[0]); self.assertIn("gba/small.zip", lines[0])
        self.assertIn("gba/big.zip", lines[1])
        self.assertEqual(seen, [["gba/big.zip"]])
```

Match the file's existing imports and isolation setup (look at how `tests/test_root.py::test_run_copies` sets `runtime.ROOT`). For `run_uploads` (s3transfer), add a unit-level test only if the file already has a harness that drives `run_uploads` against a fake transfer manager; otherwise its change is covered by Task 1's `add` → in-flight test and a code review.

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_upload.CopyOrderTest -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

- `run_copies`: `names = [j[0] for j in order]`; bar with `active=lambda: moved.active(names)`; `copy(n)` calls `moved.start(n)` first; replace the in-order loop with the same `wait(..., FIRST_COMPLETED)` loop as Task 2 (`copy` already returns `(job, error)`, so the future's index is needed for `moved.finish(n)` — keep a future → n map). `finished` counter in `[i/N]`.
- `run_uploads`: bar with `active=lambda: moved.active(names)` (`names` from `order`). In-flight starts come from `moved.add` (first bytes); `shrink_and_send` calls `moved.start(n)` first so a shrinking PNG shows. The existing `moved.finish(n)` already removes finished jobs.

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/sync_roms/upload.py tests/test_upload.py
git commit -m "feat(upload): print copies as they finish and list transfers in flight"
```

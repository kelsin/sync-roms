# Collections Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sync-roms collections page [--out FILE]` writes one self-contained HTML page listing the user's
collections (three pictures each, expandable game lists with tag emoji and copyable storage paths, filters) and
opens it.

**Architecture:** `collections_page.py` builds a JSON-able dict from `collections.load_collections()`, `tags.py`,
`names.title` and the repo art, with pictures as WebP data URIs. A repo template
`data/collections-page.html` holds the page's CSS and JS and an empty data block, which the command fills in the
copy it writes.

**Tech Stack:** Python 3.12+, Pillow (already a runtime dependency), plain HTML/CSS/JS, unittest.

**Spec:** `docs/superpowers/specs/2026-11-25-collections-page-design.md`

## Global Constraints

- Branch `feat/collections-page`, cut from `feat/tags`. Code must run on Python 3.12.
- Run everything with `uv run`; tests: `uv run python -m unittest discover -s tests` (stdin closed: `< /dev/null`).
- Test modules import `helpers` (or `isolate`) before `sync_roms`.
- Template: no external URLs (`http://`/`https://` in `src`/`href`/`url(`/`@import`), no external scripts, styles
  or fonts. The data block is exactly `<script type="application/json" id="page-data">{}</script>` in the repo.
- Data is embedded with `json.dumps(data).replace("<", "\\u003c")`, as `guide_cmd` does.
- Pictures (art id = collection `art`, else its `id`):
  - band: `themeart.art_png(art_id)`, shrunk to 150 px wide
  - box: `themeart.art_png(art_id, "art-box/Imgs_med")`
  - ToTK card: `os.path.join(themeart.ZELDA_ART, "Imgs_med", f"{art_id}.png")`

  Each becomes a `data:image/webp;base64,...` URI at WebP quality 80. A missing file is left out (key absent).
- Tags: storage being unset or unreachable (`s3.ERRORS`, `SystemExit`) leaves the page without tags and prints
  one `ui.warn`.
- Conventional Commits, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- A title or description containing `</script>` or `<b>` must not break or inject into the page. Pin it: the
  data-builder test uses a `</script>` title, and the template sets text only with `textContent`.
- A collection with zero games, or one whose games all fail a filter, is hidden while filtering and shown with
  "0 games" otherwise.
- A game whose tag id isn't defined in `tags.json` shows no emoji for it and doesn't crash.
- Copying on `file://` or plain `http` where `navigator.clipboard` is missing or rejects: fall back to a selected
  `<textarea>` and `document.execCommand("copy")`.
- A game key in a system missing from `systems.json`: the system name falls back to the key's folder.

---

### Task 1: Data builder

**Files:**
- Create: `src/sync_roms/collections_page.py`
- Test: `tests/test_collections_page.py`

**Interfaces:**
- Produces: `collections_page.page_data() -> dict` with this shape:
  ```
  {"tags": {tag_id: {"name": str, "emoji": str}},
   "systems": {system_id: system name},            # only systems that some game uses
   "collections": [{"id", "name", "description",
                    "art": {"band"?: uri, "box"?: uri, "totk"?: uri},
                    "games": [{"title", "system", "paths": [bucket, *files], "tags": [tag ids, sorted]}]}]}
  ```
  Collections keep `load_collections()` order. Games keep file order. `title` is the game's `title` if it's a
  non-empty str, else `names.title(bucket)`. `system` is the bucket key's folder. `tags` is `tags.tags_of(bucket)`
  filtered to ids that are in `tags.all_tags()`.
- Produces: `collections_page.webp_uri(path: str, width: int | None = None) -> str | None`. Returns None when the
  path is missing. With `width`, it resizes to that width keeping the aspect (`Image.LANCZOS`), never enlarging.

- [ ] **Step 1: Write failing tests** in `tests/test_collections_page.py`. Write collection files into
  `collections.collections_dir()`, and patch `tags.load` to return a dict
  `{"tags": {...}, "games": {...}, "declined": {}}`.
  - `test_games_titles_tags_paths`: a collection with a game `{"system": "snes", "bucket": "snes/Super Mario World (USA).zip", "title": "Super Mario World"}`
    and a game with `files`. Assert `paths == ["snes/Super Mario World (USA).zip"]` and the second game's
    `paths == [bucket, *files]`. Assert `tags == ["mario", "platformers"]` when `tags.json` has those plus an
    undefined id `"ghost"`. Assert `systems["snes"] == "Nintendo SNES (Super Nintendo)"` (the name from
    `store.repo_json("systems")`).
  - `test_title_falls_back_to_names_title`: a game with no title; patch `names.title` and assert it's used.
  - `test_art_uris`: a collection with `"art": "mario"` gets `band`, `box` and `totk`, each starting with
    `data:image/webp;base64,`. A collection whose art id has no files (`"art": "nope"`) has `art == {}`.
  - `test_band_is_shrunk`: decode the band URI with Pillow, assert width 150.
  - `test_no_storage_means_no_tags`: `tags.load` raises `SystemExit(2)`. Assert `tags == {}`, each game's
    `tags == []`, and one warning on stderr.
  - `test_unknown_system_name_falls_back`: a game `"zzz/x.zip"` gives `systems["zzz"] == "zzz"`.
- [ ] **Step 2: Run** `uv run python -m unittest tests.test_collections_page < /dev/null`. Expected: errors on
  import.
- [ ] **Step 3: Implement** `webp_uri` and `page_data` per the Interfaces above.
- [ ] **Step 4: Run the tests.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(collections): build the collections page data`.

### Task 2: Page template

**Files:**
- Create: `src/sync_roms/data/collections-page.html`
- Test: `tests/test_collections_page.py` (add `TemplateTest`)

**Interfaces:**
- Consumes: the `page_data()` shape from Task 1, read in the page with
  `JSON.parse(document.getElementById("page-data").textContent)`.

The page:
- Title "ROM Collections". It works on a phone (16 px gutters, no horizontal scroll). Colors are CSS variables
  on `:root`, with dark mode under `@media (prefers-color-scheme: dark)`, and `body` has an explicit background.
- Top bar:
  - a search box: case-insensitive substring on collection name or game title. A collection whose name matches
    shows all its games.
  - a system `<select>`: "All systems" plus `systems` sorted by name.
  - a row of tag chips (`emoji name`, sorted by name), each a toggle button with `aria-pressed`. A game passes
    when it has every pressed tag.
  - a "Clear" button.
  - a count line: `N collections · M games`.
- One card per collection. The three pictures sit in a row, `loading="lazy"`, `alt` = the collection name plus
  "band"/"box"/"ToTK"; pictures that are absent are skipped. Then the name, description and game count. A
  `<details>` holds the game list.
- Game rows show:
  - the title
  - the system name
  - one `<span title="tag name">emoji</span>` per tag
  - a copy button. It copies `paths.join("\n")` and shows "Copied" for 1.5 s; the clipboard fallback is in
    Review Focus. Its `title` attribute is the path(s), so hovering shows them.
- With any filter active: collections with no passing games are hidden, the others open, and only passing games
  are shown. Without a filter, everything shows and is closed.
- With no collections it shows "No collections yet."
- All text is set with `textContent`, never `innerHTML` with data.

- [ ] **Step 1: Write failing tests** `TemplateTest`:
  - `test_empty_data_block`: the file contains the exact data block from Global Constraints, once.
  - `test_no_external_urls`: no `http://` or `https://` anywhere in the file.
  - `test_no_innerhtml`: `"innerHTML"` doesn't appear.
- [ ] **Step 2: Run them.** Expected: FAIL (file missing).
- [ ] **Step 3: Write the template.**
- [ ] **Step 4: Run them.** Expected: PASS. Then fill the template with `page_data()` from a test fixture (two
  collections, tags, one `</script>` title) into the scratchpad. Open it in the built-in browser
  (`file://`), and check the filters, the hover names, copy (read back with
  `navigator.clipboard.readText` or check that the fallback ran), dark mode and the 375 px width. Take
  screenshots for the reviewer.
- [ ] **Step 5: Commit** `feat(collections): add the collections page template`.

### Task 3: Command, help, README

**Files:**
- Modify: `src/sync_roms/collections_page.py` (add `write_page`)
- Modify: `src/sync_roms/commands.py`: `collections_page` fn near `collections_edit`, and the subparser under
  `colsub`
- Modify: `src/sync_roms/cli.py`: `TOPICS["collections"]` gets `"edit, page"` where it lists second words; the
  `collections` help text gets a line for `page`. Update `SUBCOMMANDS` if it lists second words.
- Modify: `README.md`: a Commands table row
  `| \`collections page\` | write a shareable HTML page of your collections and open it | \`collection\` |`, and a
  short paragraph under "Collections" saying the page holds your game lists and storage paths and is safe to share
  only if you're fine with that.
- Modify: `CLAUDE.md`: add `collections-page.html` to Repo data, and `share/collections/index.html` (written by
  `collections page`, served by `collections share`) to Personal data.
- Test: `tests/test_collections_page.py` (add `CommandTest`), and the existing `tests/test_readme.py` and
  `tests/test_completion.py`

**Interfaces:**
- Produces: `collections_page.write_page(path: str) -> None`. It reads the template, replaces the empty data
  block with the embedded `page_data()` (once), and writes it atomically with `store.write_text`, making the
  parent folders.
- The command: `sync-roms collections page [--out FILE]`. It uses `common(p, card=False)` if that is how the
  read-only commands get `--quiet`, and refuses `--dry-run` like `guide`. With no `--out` it writes
  `os.path.join(store.data_dir(), "share", "collections", "index.html")` (the folder Task 4 serves; define
  `collections_page.DEFAULT_PATH()` returning it). It prints the path and opens the file in the browser
  (with or without `--out`). If opening fails it calls
  `ui.fail("Couldn't open a browser: open the file above yourself", 1)`. Returns 0.

- [ ] **Step 1: Write failing tests** `CommandTest`:
  - `test_writes_and_opens`: run `cli.main(["collections", "page"])` with `webbrowser.open` patched to return
    True. The cache file exists, holds one collection's name inside the data block, and the empty block is gone.
    `open` is called with its `file://` URI.
  - `test_out_writes_elsewhere`: `--out <tmp>/x/page.html` writes there (folders made), not to the default path,
    and opens it.
  - `test_script_tag_escaped`: a collection titled `</script><b>` doesn't add a second `</script>` before the
    template's own.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** `write_page`, the command, the help, README and CLAUDE.md.
- [ ] **Step 4: Run the full suite** `uv run python -m unittest discover -s tests < /dev/null`. Expected: all
  pass, `test_readme` and completion included.
- [ ] **Step 5: Commit** `feat(collections): add collections page command`.

### Task 4: Share over Tailscale

**Files:**
- Create: `src/sync_roms/tailshare.py`
- Modify: `src/sync_roms/commands.py` (`collections share`, `collections unshare`), `src/sync_roms/cli.py`
  (help and second words), `README.md` (two Commands rows plus a paragraph under Collections), `CLAUDE.md`
  (Personal data: `share/collections/index.html`, written by `collections share`, the only folder it serves)
- Test: `tests/test_tailshare.py`

**Interfaces:**
- Consumes: `collections_page.write_page(path)` from Task 3.
- Produces:
  - `tailshare.SHARE_DIR() -> str`, the folder of `collections_page.DEFAULT_PATH()`, which is `os.path.join(store.data_dir(), "share", "collections")`
  - `tailshare.PATH = "/collections"`
  - `tailshare.serving() -> bool`: reads `["tailscale", "serve", "status", "--json"]` and returns True when any
    `Web.<host:port>.Handlers` has the key `PATH`. Empty output or `{}` means False.
  - `tailshare.share() -> tuple[str, bool, bool]`: writes the page with `collections_page.write_page` only when
    `<SHARE_DIR>/index.html` is missing. It runs `["tailscale", "serve", "--bg", "--set-path", PATH, SHARE_DIR()]`
    only when `serving()` is False. Then it reads `["tailscale", "status", "--json"]` and returns
    `(f"https://{Self.DNSName.rstrip('.')}{PATH}/", built, started)`.
  - `tailshare.unshare() -> bool`: when `serving()`, it runs
    `["tailscale", "serve", "--https=443", "--set-path", PATH, "off"]` and returns True; otherwise it returns False.
  - Both run through `subprocess.run(..., capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)`.
    `shutil.which("tailscale")` being None calls `ui.fail("tailscale isn't installed or not on PATH", 1)`. A
    non-zero exit calls `ui.fail(f"tailscale serve failed: {stderr.strip()}", 1)`.
- Produces: `tailshare.copy_to_clipboard(text: str) -> bool`. It tries the first of `pbcopy`, `clip`, `wl-copy`,
  `xclip -selection clipboard` that `shutil.which` finds, feeding `text` on stdin. It returns True on exit 0, and
  False when none is found or the command fails (never an error).
- The commands are `collections share` and `collections unshare`. `share` copies the link with
  `copy_to_clipboard` and adds ` (copied to the clipboard)` to its `Sharing at`/`Already shared at` line when that
  worked. `share` prints `Built <path>` when it built the
  page, then `Sharing at <link>` (or `Already shared at <link>`). `unshare` prints
  `Stopped sharing the collections page.` or `The collections page isn't shared.`; both exit 0. To refresh a
  shared page, run `collections page`, which rewrites the served file. They refuse `--dry-run` like `guide`. Never call `tailscale serve reset`.

- [ ] **Step 1: Write failing tests** with `subprocess.run` and `shutil.which` patched:
  - `test_share_writes_and_serves`: with no page and no serve entry, the file is written under the data folder's
    `share/collections/index.html`, the serve argv is as above, and it returns `built` and `started` True.
  - `test_share_keeps_existing_page_and_serve`: with the page present and the status JSON
    `{"Web": {"box.tail1.ts.net:443": {"Handlers": {"/collections": {"Path": "x"}}}}}`, nothing is written or
    served, and it returns `(link, False, False)`.
  - `test_clipboard`: with `which` finding only `pbcopy`, it runs `["pbcopy"]` with `input=link` and returns True.
    With nothing found it returns False and makes no call.
  - `test_share_command_copies_link`: `cli.main(["collections", "share"])` prints a line ending
    `(copied to the clipboard)` when `copy_to_clipboard` returns True.
  - `test_unshare_when_not_serving`: status `{}` gives False and no `off` call. The returned link is `https://box.tail1.ts.net/collections/` for
    `DNSName "box.tail1.ts.net."`.
  - `test_unshare_only_turns_off_its_path`: while serving, the argv is as above, it returns True, and no call
    contains `"reset"`.
  - `test_missing_tailscale_fails`: `which` returns None, so `SystemExit` with code 1 and no `subprocess.run` call.
  - `test_serve_error_surfaces`: returncode 1 with stderr `"HTTPS not enabled"` gives exit 1 with that text on
    stderr.
  - `test_serves_only_share_folder`: the served path is `SHARE_DIR()`, never `store.data_dir()`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** `tailshare.py`, the commands, help, README and CLAUDE.md.
- [ ] **Step 4: Run the full suite.** Expected: all pass.
- [ ] **Step 5: Commit** `feat(collections): share the collections page over tailscale`.

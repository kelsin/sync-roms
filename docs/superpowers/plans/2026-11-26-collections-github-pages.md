# Collections page on GitHub Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sync-roms collections publish` puts a public, path-free build of the collections page into a GitHub Pages repo for `https://sync-roms.games/collections/<user>/`, with a user list at the root.

**Architecture:** The page template splits into `page.html`/`page.css`/`page.js`. The local build inlines them (one self-contained file, as now); the public build writes them as files plus `art/*.webp`, drops game paths and sets `home`. A new `pages_site.py` keeps a clone of the Pages repo in the cache, writes the user's folder, the root user list, the `/collections/` redirect, `CNAME` and `.nojekyll`, and commits and pushes when something changed.

**Tech Stack:** Python 3.12+ stdlib, `git` via `subprocess`, Pillow (already used), vanilla JS/CSS.

**Spec:** `docs/superpowers/specs/2026-11-26-collections-github-pages-design.md`

## Global Constraints

- Run everything with `uv run` (`uv run python -m unittest tests.test_collections_page`); code must run on Python 3.12.
- Test modules import `helpers` (or `isolate`) before `sync_roms`.
- Never put a real game list in the `sync-roms` repo; tests use made-up games only.
- The local page stays one self-contained file: no `http://`/`https://` URLs, no `innerHTML`, no external files.
- The public page has no game `paths` anywhere in its data and no Copy column.
- Default `pages_repo`: `git@github.com:kelsin/sync-roms.games.git`; domain `sync-roms.games`; clone at `<data dir>/cache/pages/`.
- Conventional Commits, lowercase imperative; end every commit with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never hand-edit `__version__`, `CHANGELOG.md` or `.release-please-manifest.json`.

## Review Focus

- A `--user` (or login name) with uppercase, spaces, `/`, `..` or other non-slug characters: refused with exit 2 and a message, never written as a path.
- A freshly created, empty Pages repo (no commits, no `main`): the first publish works and pushes `main`.
- A cache clone left dirty or ahead by a failed earlier publish: the next publish resets it to `origin/main` and goes on.
- A collection removed since the last publish: its art files are gone from the user's folder after the next publish (the folder is rebuilt, not merged).
- `git` missing, or clone/fetch/push failing (no network, no permission): a clear error and nonzero exit, nothing half-pushed reported as done.

---

### Task 1: Split the template; back link and optional Copy column

**Files:**
- Delete: `src/sync_roms/data/collections-page.html`
- Create: `src/sync_roms/data/collections-page/page.html`, `page.css`, `page.js`
- Modify: `src/sync_roms/collections_page.py` (`TEMPLATE`, `render`)
- Modify: `tests/test_collections_page.py`

**Interfaces:**
- Produces: `collections_page.TEMPLATE_DIR` (the folder), `collections_page.template_files() -> dict[str, str]` (`{"page.html", "page.css", "page.js": text}`), `collections_page.render(data=None) -> str` (self-contained HTML; `data` defaults to `page_data()`), `collections_page.fill(html: str, data: dict) -> str` (puts the JSON, `<` escaped as `<`, in the empty `page-data` block).

- [ ] **Step 1: Write the failing tests** in `tests/test_collections_page.py`. Point the template test class at the three files (read and concatenate for the existing needle tests) and add:

```python
def test_page_html_links_its_files(self):
    html = collections_page.template_files()["page.html"]
    self.assertIn('<link rel="stylesheet" href="page.css">', html)
    self.assertIn('<script src="page.js"></script>', html)

def test_render_is_self_contained(self):
    html = collections_page.render({"tags": {}, "systems": {}, "collections": []})
    self.assertNotIn('href="page.css"', html)
    self.assertNotIn('src="page.js"', html)
    self.assertIn(collections_page.template_files()["page.css"].strip()[:40], html)
    self.assertIn("<style>", html)

def test_back_link_and_copy_column_are_conditional(self):
    js = collections_page.template_files()["page.js"]
    self.assertIn("data.home", js)
    self.assertIn("All users", js)
    self.assertIn("hasPaths", js)
```

Update `test_script_tag_escaped` to compare against `render()` of an empty data block instead of the old single template file.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_collections_page -v`. Expected: the new tests FAIL (`template_files` missing).

- [ ] **Step 3: Split the template and implement.**
  - Move the contents of the `<style>` block to `page.css` and of the main `<script>` block to `page.js`. In `page.html`, the style block becomes `<link rel="stylesheet" href="page.css">`, the script becomes `<script src="page.js"></script>`, and the `page-data` JSON block stays in place before it.
  - `render(data)` replaces those two exact tags with `<style>\n{css}</style>` and `<script>\n{js}</script>`, then `fill`s. A `</script>` inside `page.js` must not be possible (assert in a test that `page.js` has none).
  - In `page.js`, when `data.home` is a string, add an `<a class="home" href="{data.home}">← All users</a>` before the `<h1>` in the header (built with `el`, no `innerHTML`), styled in `page.css` to match the muted header text.
  - `var hasPaths = list.some(c => (c.games || []).some(g => (g.paths || []).length))` (ES5 style like the rest of the file). Without paths, leave out the empty `col-copy` header cell and each row's Copy cell.

- [ ] **Step 4: Run** `uv run python -m unittest tests.test_collections_page tests.test_tailshare -v`. Expected: PASS.

- [ ] **Step 5: Check** in the browser pane that `uv run sync-roms collections page --out <scratchpad>/local.html` (with a made-up collection in a throwaway data dir is fine) looks and works as before, with no back link.

- [ ] **Step 6: Commit** `refactor(collections): split the page template into html, css and js files`.

---

### Task 2: Public build of the page

**Files:**
- Modify: `src/sync_roms/collections_page.py`
- Test: `tests/test_collections_page.py`

**Interfaces:**
- Consumes: `template_files()`, `fill()` from Task 1.
- Produces: `collections_page.webp_bytes(path, width=None, crop=None) -> bytes | None` (what `webp_uri` encodes; `webp_uri` now wraps it); `collections_page.page_data(public=False, art_dir=None) -> dict`; `collections_page.write_public(out_dir: str, home: str = "/") -> None`.

- [ ] **Step 1: Write the failing tests** (class `Public(Page)` reusing `Page`'s setup and the art fixtures `test_art_uris` uses):

```python
def test_public_data_has_no_paths_and_a_home(self):
    self.save(games=[{"system": "snes", "bucket": SMW, "title": "x"}])
    out = self.enterContext(tempfile.TemporaryDirectory())
    collections_page.write_public(out, home="/")
    data = page_json(os.path.join(out, "index.html"))  # helper: parses the page-data block
    self.assertEqual(data["home"], "/")
    self.assertNotIn("paths", data["collections"][0]["games"][0])
    self.assertNotIn("Super Mario World (USA).zip", open(os.path.join(out, "index.html"), encoding="utf-8").read())

def test_public_writes_separate_files(self):
    self.save(art="mario")  # an art id that has a band picture
    out = self.enterContext(tempfile.TemporaryDirectory())
    collections_page.write_public(out)
    self.assertEqual(sorted(f for f in os.listdir(out) if os.path.isfile(os.path.join(out, f))), ["index.html", "page.css", "page.js"])
    art = page_json(os.path.join(out, "index.html"))["collections"][0]["art"]
    self.assertEqual(art["band"], "art/mario-band.webp")
    self.assertTrue(os.path.isfile(os.path.join(out, "art", "mario-band.webp")))
    self.assertNotIn("data:image", open(os.path.join(out, "index.html"), encoding="utf-8").read())

def test_public_removes_stale_files(self):
    out = self.enterContext(tempfile.TemporaryDirectory())
    os.makedirs(os.path.join(out, "art")); open(os.path.join(out, "art", "gone-band.webp"), "wb").close()
    collections_page.write_public(out)
    self.assertFalse(os.path.exists(os.path.join(out, "art", "gone-band.webp")))

def test_local_data_unchanged(self):
    self.save(games=[{"system": "snes", "bucket": SMW, "title": "x"}])
    data = collections_page.page_data()
    self.assertNotIn("home", data)
    self.assertEqual(data["collections"][0]["games"][0]["paths"], [SMW])
```

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_collections_page -v`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement.**
  - `_art(art_id, art_dir=None)`: with `art_dir`, write each kind's WebP bytes to `<art_dir>/<art_id>-<kind>.webp` and return `"art/<art_id>-<kind>.webp"`; without, `data:` URIs as now. Two collections sharing an art id write the same file once.
  - `page_data(public=True, ...)` leaves `paths` out of every game and adds `"home"` only through `write_public`.
  - `write_public(out_dir, home)`: remove `out_dir` entirely if it exists, recreate it, write `page.html` (filled, with `home` in the data) as `index.html` plus `page.css` and `page.js` verbatim, art into `out_dir/art/`. Use `store.write_text` for text files.

- [ ] **Step 4: Run** `uv run python -m unittest tests.test_collections_page -v`. Expected: PASS.

- [ ] **Step 5: Commit** `feat(collections): build a public page with separate files and no game paths`.

---

### Task 3: The Pages site and `collections publish`

**Files:**
- Create: `src/sync_roms/pages_site.py`
- Create: `src/sync_roms/data/pages-site/index.html` (user list template), `src/sync_roms/data/pages-site/redirect.html`
- Modify: `src/sync_roms/commands.py` (parser, `collections_publish_cmd`, `CONFIG_KINDS["pages_repo"] = str`)
- Modify: `src/sync_roms/cli.py` (`TOPICS["collections"]`, `SUBCOMMANDS["collections"]` to `"edit|page|publish|retitle|share|unshare"` and its description)
- Modify: `README.md` (Commands table row for `collections publish`; Settings section: `pages_repo` with its default; a short "Publishing to GitHub Pages" pointer to the guide)
- Modify: `CLAUDE.md` (Data files repo data: `collections-page/` and `pages-site/`; Personal data `cache/`: `pages/`, the Pages repo clone; `settings.json`: `pages_repo`)
- Create: `docs/github-pages.md`
- Test: `tests/test_pages_site.py`

**Interfaces:**
- Consumes: `collections_page.write_public(out_dir, home)` from Task 2.
- Produces: `pages_site.DOMAIN = "sync-roms.games"`, `pages_site.DEFAULT_REPO = "git@github.com:kelsin/sync-roms.games.git"`, `pages_site.CLONE_DIR() -> str` (`<data dir>/cache/pages`), `pages_site.valid_user(name: str) -> bool` (`^[a-z0-9][a-z0-9_-]{0,38}$`), `pages_site.build(site_dir: str, user: str) -> None`, `pages_site.publish(user: str, dry_run: bool = False) -> tuple[bool, str]` (`(changed, url)`), url `https://sync-roms.games/collections/<user>/`.

- [ ] **Step 1: Write the failing tests** in `tests/test_pages_site.py` (`helpers.DataDir`; `tags.load` patched as in `test_collections_page`; a bare repo `git init --bare -b main` in a temp dir as `pages_repo`; `GIT_AUTHOR_NAME/EMAIL`, `GIT_COMMITTER_NAME/EMAIL` set in `os.environ` for the test):

```python
def test_build_layout(self):
    site = tmpdir()
    os.makedirs(os.path.join(site, "collections", "alice"))
    open(os.path.join(site, "collections", "alice", "index.html"), "w").close()
    pages_site.build(site, "kelsin")
    self.assertEqual(read(site, "CNAME").strip(), "sync-roms.games")
    self.assertTrue(os.path.exists(os.path.join(site, ".nojekyll")))
    root = read(site, "index.html")
    self.assertIn('href="collections/alice/"', root); self.assertIn('href="collections/kelsin/"', root)
    self.assertLess(root.index("alice"), root.index("kelsin"))
    self.assertIn('url=/', read(site, "collections", "index.html"))
    self.assertTrue(os.path.isfile(os.path.join(site, "collections", "kelsin", "page.js")))

def test_invalid_users_refused(self):
    for name in ("Kelsin", "a b", "../x", "a/b", "", "-x"):
        self.assertFalse(pages_site.valid_user(name), name)
    self.assertEqual(self.run_cmd("collections", "publish", "--user", "../x")[0], 2)

def test_first_publish_to_empty_repo_then_no_change(self):
    changed, url = pages_site.publish("kelsin")
    self.assertTrue(changed); self.assertEqual(url, "https://sync-roms.games/collections/kelsin/")
    self.assertIn("collections/kelsin/index.html", git_ls_tree(self.bare, "main"))
    self.assertFalse(pages_site.publish("kelsin")[0])

def test_dirty_clone_is_reset(self):
    pages_site.publish("kelsin")
    open(os.path.join(pages_site.CLONE_DIR(), "junk.txt"), "w").close()
    self.save_collection("Another")
    self.assertTrue(pages_site.publish("kelsin")[0])
    self.assertNotIn("junk.txt", git_ls_tree(self.bare, "main"))

def test_dry_run_pushes_nothing(self):
    changed, _ = pages_site.publish("kelsin", dry_run=True)
    self.assertTrue(changed)
    self.assertEqual(git_ls_tree(self.bare, "main"), [])  # nothing pushed

def test_push_failure_exits_nonzero(self):
    pages_site.publish("kelsin")
    shutil.rmtree(self.bare)
    self.assertNotEqual(self.run_cmd("collections", "publish")[0], 0)
```

Plus a `run_cmd("collections", "publish")` test where `getpass.getuser` is patched to `"kelsin"` and the output includes the URL.

- [ ] **Step 2: Run** `uv run python -m unittest tests.test_pages_site -v`. Expected: FAIL (`pages_site` missing).

- [ ] **Step 3: Implement `pages_site.py`.**
  - `build(site_dir, user)`: `collections_page.write_public(<site>/collections/<user>, home="/")`; write `CNAME` (`sync-roms.games\n`), empty `.nojekyll`, `collections/index.html` from `redirect.html` (meta refresh `0; url=/` plus a link to `/`), and `index.html` from the user-list template filled with every `collections/*/` that holds `index.html`, sorted, each `<li><a href="collections/<name>/"><name></a></li>` with names HTML-escaped. Templates use the collections page's colours, light and dark.
  - `publish(user, dry_run)`: the repo is `usersettings.load_settings().get("pages_repo") or DEFAULT_REPO`. Without a clone, `git clone <repo> <CLONE_DIR>`; then `git fetch origin`; if `origin/main` exists, `git checkout -B main origin/main` and `git reset --hard origin/main`, otherwise `git symbolic-ref HEAD refs/heads/main` (an empty repo); always `git clean -fdx`. Then `build`, `git add -A`, and `git status --porcelain`: empty means `(False, url)`. Otherwise, without `dry_run`, `git commit -m "publish collections for <user>"` and `git push origin main`. Every git call goes through one helper that runs `subprocess.run([... ], capture_output=True, text=True)` and calls `ui.fail("git <args> failed: <stderr>", 1)` on a nonzero exit, or on `FileNotFoundError` with `"git isn't installed"`.
  - `collections_publish_cmd(args)`: `user = args.user or getpass.getuser()`; an invalid user is `ui.fail(..., 2)` naming the rule and suggesting `--user`. Print `Published <url>` / `Already up to date: <url>` / for a dry run `Would publish <url>` (with the changed files from `git status --porcelain`) or `Nothing to publish`. The parser is `colsub.add_parser("publish")` with `common(p, card=False)`, `--user NAME`, `--dry-run` (not in the dry-run refusal list).

- [ ] **Step 4: Write the help, README, CLAUDE.md lines and `docs/github-pages.md`.** The guide covers, in order: create the public repo `sync-roms.games` on GitHub (empty, no README); `sync-roms config set pages_repo git@github.com:<you>/sync-roms.games.git` if it isn't the default; run `sync-roms collections publish` once so `main` exists; in the repo's Settings → Pages, set Source to "Deploy from a branch", `main`, `/ (root)`; set Custom domain `sync-roms.games` (the `CNAME` file publish writes keeps it); verify the domain under the account's Settings → Pages (the TXT record GitHub shows); DNS at the registrar: apex `A` 185.199.108.153, 185.199.109.153, 185.199.110.153, 185.199.111.153, `AAAA` 2606:50c0:8000::153, 2606:50c0:8001::153, 2606:50c0:8002::153, 2606:50c0:8003::153, `www` `CNAME` `<you>.github.io`; wait for the certificate and tick "Enforce HTTPS"; check `https://sync-roms.games/`, `/collections`, `/collections/kelsin/`. It notes that the public page has no file names or storage paths, but does list your games, and that each publish replaces only your own folder.

- [ ] **Step 5: Run** `uv run python -m unittest tests.test_pages_site tests.test_collections_page tests.test_readme -v`, then `uv run python tools/run_tests.py`. Expected: all PASS.

- [ ] **Step 6: Check in the browser pane**: build a site into the scratchpad with made-up collections (`pages_site.build`), serve it with `uv run python -m http.server -d <dir>`, open `/`, click through to `/collections/kelsin/`, confirm the back link, the art, no Copy column, and that `/collections/` goes to `/`.

- [ ] **Step 7: Commit** `feat(collections): publish the collections page to github pages`.

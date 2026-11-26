# Game box art on the published collections site

Goal: every game row on the public collections page (`collections publish`) shows a small picture of its scraped art, with a 300px picture on hover, focus or tap, and every published page credits ScreenScraper at the bottom. The local page (`collections page`, `collections share`) is unchanged: no game art, no credit.

User decisions (binding):
- Box art on the GitHub Pages site only, never on the local page.
- Thumbnails in a fixed-size box (`object-fit: contain`) so rows stay even whatever the picture's shape.
- No per-game ScreenScraper links (no game ids are stored). One attribution footer at the bottom of every published page: each user's collections page and the site's root list of users.

## Global constraints

- Python must run on 3.12. Run tests with `uv run python tools/run_tests.py` (or `uv run python -m unittest tests.test_collections_page tests.test_pages_site`), stdin closed (`< /dev/null`).
- Test modules import `isolate` (or `helpers`) before `sync_roms`; follow the existing tests in `tests/test_collections_page.py` and `tests/test_pages_site.py`.
- The collections page templates (`src/sync_roms/data/collections-page/page.*`) must keep containing no `http://` or `https://` (`TemplateTest.test_no_external_urls`) and no `innerHTML`. So the credit's URL comes from the page data, not the template.
- The public page must never contain storage paths (bucket keys or ROM file names): game art file names are a hash of the bucket key.
- Match the surrounding style: plain ES5 JS (`var`, `function`), the existing `el()` helper, CSS variables from `page.css`.
- Conventional Commits, lowercase imperative. End commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Don't touch `__version__`, `CHANGELOG.md` or `.release-please-manifest.json`.

## Task 1: game art and credit in the public page data

Files: `src/sync_roms/collections_page.py`, `tests/test_collections_page.py`.

1. In `page_data(public=False, art_dir=None, strict=False)`: when `art_dir` is given (only `write_public` passes it), give each game that has scraped art an `"img"` field `"art/games/<h>"`, where `<h>` is `hashlib.sha1(bucket.encode()).hexdigest()[:16]`. The page appends `-s.webp` (small) and `-l.webp` (large). Write `<art_dir>/games/<h>-s.webp` (96 px wide) and `<h>-l.webp` (300 px wide) with the existing `webp_bytes(path, width)` (it never enlarges), from the local file `previews.game_thumb(bucket)` returns. When `game_thumb` returns None, the game gets no `"img"`. Without `art_dir` no game gets `"img"` and `previews` isn't called.
2. A bucket in several collections is written once (keep a dict bucket -> img-or-None across collections).
3. Make the files in parallel: collect the unique buckets first, then `concurrent.futures.ThreadPoolExecutor(max_workers=8)` mapping a function that returns `img` or None. Print one line before (`🖼️  Game art for N games…` via `print`, flush) since a first publish can take a minute.
4. In `write_public`, also set `data["credit"] = {"text": "Game art from ScreenScraper", "url": "https://www.screenscraper.fr/"}` next to `data["home"]`. Put the text and URL in module constants `CREDIT_TEXT`, `CREDIT_URL` (pages_site reuses them).
5. Tests (mock `previews.game_thumb` to return a small PNG made with Pillow in a temp dir, or None):
   - `write_public` writes `art/games/<h>-s.webp` 96 px wide and `-l.webp` ≤ 300 px wide, and the game's `img` is `art/games/<h>`; neither the file names nor `index.html` contain the ROM file name.
   - a game whose `game_thumb` is None has no `img`.
   - the same bucket in two collections calls `game_thumb` once and gets the same `img`.
   - `page_data()` without `art_dir` has no `img` on any game and never calls `game_thumb`.
   - `write_public` data has `credit` with `CREDIT_URL`; `page_data()` has no `credit`.

Commit: `feat(collections): game box art on the published page`

## Task 2: thumbnail column, hover picture and footer in the page

Files: `src/sync_roms/data/collections-page/page.js`, `page.css`, `page.html`, `tests/test_collections_page.py` (TemplateTest).

1. `hasArt` = any game in any collection has `img` (like `hasPaths`). Only then does `buildBody` add a first column (`col-art`, empty header, not sortable) and `gameRow` a first cell.
2. The cell holds `<span class="thumb">`: with `img`, an `<img loading="lazy" alt="" src="<img>-s.webp">`, `tabIndex = 0`, `aria-label` "Box art of <title>"; without, class `thumb none` holding `🎮` (no tabIndex, no handlers).
3. One body-level popover `<div class="art-pop">` (an `<img>` and a caption `<div class="cap">` with the title), created once like the existing `pop`/`tip`. Show it on the thumb's `mouseenter` and `focus`, hide on `mouseleave` and `blur`; `click` toggles it (touch) and stops propagation. Its `src` is `<img>-l.webp`. Place it right of the thumb, or left when it doesn't fit, vertically centred on the thumb and kept 8 px inside the window; re-place on the large image's `load`. Hide it on scroll and on any other document click, as the existing size popover is (extend `hidePop` and the existing listeners rather than adding duplicates).
4. CSS: `.games .col-art { width: 56px; padding-right: 0; }`; `.thumb` a 42x56 flex box, centred, `border-radius: 4px`, `background: var(--surface-2)`, `border: 1px solid var(--border)`, `overflow: hidden`, `cursor: zoom-in`; `.thumb img { max-width: 100%; max-height: 100%; display: block; }` (contain, rows stay even); `.thumb.none { cursor: default; color: var(--muted); font-size: 18px; }`; `.art-pop` fixed, z-index 7, `pointer-events: none`, surface background, border, `border-radius: 10px`, a soft shadow, `padding: 8px`, `width: 316px`; `.art-pop img { display: block; width: 300px; height: auto; border-radius: 6px; }`; `.art-pop .cap { font-size: 12px; color: var(--muted); padding: 6px 2px 0; }`. In the `max-width: 640px` block: `.games .col-art { width: 46px; }` and `.thumb { width: 34px; height: 46px; }`.
5. Footer: add `<footer class="credit" id="credit" hidden></footer>` after `.wrap`'s `<p class="empty">` in `page.html`. In `page.js`, when `data.credit` has `text` and `url`, fill it with an `<a>` (`href` = url, `rel="noopener"`, text = text) and unhide it. CSS: `.credit { margin-top: 32px; text-align: center; font-size: 13px; color: var(--muted); } .credit a { color: inherit; }`.
6. TemplateTest: assert `page.js` contains `hasArt`, `art-pop`, `-s.webp`, `-l.webp`, `data.credit`; `page.html` contains `id="credit"`. The existing no-URL and no-innerHTML tests must still pass.

Commit: `feat(collections): thumbnail column with hover box art and credit footer`

## Task 3: credit on the site's root page, docs

Files: `src/sync_roms/data/pages-site/index.html`, `src/sync_roms/pages_site.py`, `tests/test_pages_site.py`, `CLAUDE.md`, `README.md`.

1. `index.html`: add `<!-- credit -->` after the `</ul>` inside `.wrap`, and a `.credit` style (`margin-top: 32px; text-align: center; font-size: 13px; color: var(--muted);` and `.credit a` reset so it doesn't get the list's block-button `a` style: `display: inline; padding: 0; background: none; border: 0; font-weight: normal; color: inherit; text-decoration: underline;`).
2. `pages_site.build` replaces `<!-- credit -->` with `<p class="credit"><a href="{CREDIT_URL}" rel="noopener">{CREDIT_TEXT}</a></p>` (html-escaped, from `collections_page`).
3. Test in `test_build_layout` (or a new test): the root `index.html` contains `collections_page.CREDIT_URL` and `CREDIT_TEXT`.
4. CLAUDE.md: in the `collections-page/` bullet of "Repo data", after "`collections_page.write_public` writes the same three files apart, with art as `art/*.webp`", add that it also writes each game's scraped art (`previews.game_thumb`) as `art/games/<sha1 of the bucket key, 16 hex>-s.webp` (96 px) and `-l.webp` (300 px), and a `credit` to ScreenScraper that the page shows as a footer; the local page gets neither. In the `pages-site/` bullet, mention the credit line. Keep the file's terse style.
5. README: in the `collections publish` paragraph (the one starting "`sync-roms collections publish [--user NAME] [--dry-run]` publishes a public copy"), add one sentence: the public copy also shows each game's scraped box art (a larger picture on hover or tap) and credits ScreenScraper; the local page has neither.
6. Run the whole suite: `uv run python tools/run_tests.py < /dev/null`.

Commit: `feat(collections): credit screenscraper on the site's root page`

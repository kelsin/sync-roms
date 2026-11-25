# Collections page

## Intent

A single HTML file showing the user's collections, so friends can browse which collections exist and what is in
them. It can be shared as one file or hosted anywhere. It is for browsing only: nothing on the page changes data.

## Goals

- `sync-roms collections page [--out FILE]` writes the page and opens it in the browser. Without `--out` it
  writes `share/collections/index.html` in the data folder, the folder `share` serves, so rerunning it refreshes a
  shared page.
- One row per collection (from `collections.load_collections`) with its name, description, game count and its
  three pictures: the ES-DE band (`art-book-next/art/<id>.png`), the box (`art-book-next/art-box/Imgs_med/<id>.png`)
  and the ToTK card (`totk-james/collections/Imgs_med/<id>.png`). The art id is the collection's `art`, or else its
  own id. A picture that doesn't exist is left out.
- Each collection expands to its game list. Each game row shows:
  - the title (the game's `title`, else `names.title(key)`)
  - the system name
  - the game's tag emoji from `tags.json`; hovering an emoji shows the tag's name
  - a copy button that copies the game's storage path (`snes/Super Mario World (USA).zip`). A game with extra
    `files` copies all of its paths, one per line.
- Filters:
  - a text box matching collection names and game titles
  - a system picker
  - tag chips (emoji plus name) that the user toggles. A game passes when it has every chosen tag.

  Collections with no matching games are hidden, and while a filter is active the matching collections open
  automatically.

- `sync-roms collections share` builds the page into `share/collections/index.html` in the data folder when it
  isn't there yet (only
  that folder is served, never the data folder itself, which holds `settings.json` with passwords and keys). It
  serves that folder on the tailnet with `tailscale serve --bg --set-path /collections <folder>`, and prints the
  link `https://<Self.DNSName without the trailing dot>/collections/` from `tailscale status --json`. It also copies the link to the clipboard (`pbcopy`, `clip`, `wl-copy` or `xclip`, whichever exists;
  skipped quietly when none does). It starts
  serving only when `/collections` isn't served already (`tailscale serve status --json`).
- `sync-roms collections unshare`, when `/collections` is served, runs `tailscale serve --https=443 --set-path /collections off`. That removes
  only this entry and leaves other serve entries alone (never `tailscale serve reset`). The page file stays.

## Non-goals

- Editing anything, or links to download ROMs.
- Showing cards, sets or anything beyond collections, tags and titles.

## Constraints

- Self-contained: no external scripts, styles, fonts or requests. The data goes in as JSON in a
  `<script type="application/json">` block (`<` escaped as in `guide_cmd`). The pictures go in as `data:` WebP
  URIs made with Pillow.
- The template is a repo file, `src/sync_roms/data/collections-page.html`, with an empty data block (`{}`), so the
  repo holds no real game list. The command fills in the data in the copy it writes.
- Tags come from `tags.py` (storage, through `shared.py`). If storage is unset or unreachable, the page is still
  written, with no tags and a warning.
- The page works opened from disk (`file://`). Copying uses `navigator.clipboard` with a fallback that selects the
  text, since `file://` and plain-`http` hosts can lack clipboard access.
- New command wiring per CLAUDE.md: the subparser goes under `collections` and in `cli.TOPICS`/`cli.SUBCOMMANDS`.
  Add a README row if the Commands table lists second words.

- Sharing needs the `tailscale` CLI on PATH. Without it, `share`/`unshare` exit 1 saying so. A failing
  `tailscale` command exits 1 with its stderr; the first run may need HTTPS certificates turned on in the admin
  console, and Tailscale's own message says so.

## Approaches

- **One self-contained HTML file with embedded data and shrunk WebP pictures (picked).** It's easy to share, and
  shrinking the pictures keeps the file around 1–2 MB.
- A folder with the page plus image files: smaller and full-size pictures, but it isn't one file to send.
- A page using a CDN framework: breaks offline and makes outside requests.

## Builder's calls

- Picture sizes: the band shrunk to about 150 px wide, the box and the ToTK card at their `Imgs_med` 210×300. WebP
  quality around 80.
- Module split: a `collections_page.py` that builds the data and writes the file, and a thin command in
  `commands.py`.
- Look and layout of the page (light and dark, works on a phone).
- Tests: the data builder (titles, tags, art lookup, missing art, no-storage fallback), that the template has the
  empty data block and no external URLs, and the command writing the file.

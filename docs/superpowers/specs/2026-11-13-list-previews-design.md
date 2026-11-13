# Image previews while browsing lists

## Intent

Lists show the highlighted row's picture beside them, like the theme-art picker already does, so browsing collections,
systems and games shows what they look like.

## What shows

| Row | Image |
|---|---|
| Collection | Its `art` PNG from the repo (`themeart.art_png`); none when it has no art |
| System | The Art Book Next outline for its `folders.esde` id (`_inc/systems/artwork-outline/<id>.png` in the theme archive) |
| Game | The first scraped image found, in order: `covers`, `miximages`, `titlescreens`, `screenshots` (`scrapes/<system>/<type>/<ROM path>.<ext>`) |

Rows without an image show a blank pane, as the picker does today. The pane only exists where `filter_list` already
draws images (Kitty/Sixel, not tmux).

## Where

Every list whose rows are collections, systems or games: the card's collections and systems lists, the collection
editor's collection list, the card's per-system game editor, the collection and set "games" lists, and the
"which system?" pickers (collection/set editors, upload, diff). Non-item rows (➕ New, ✅ Done, ...) show none.

## How

- New module `previews.py` with `collection(art_id)`, `system(system)` and `game(system, key)`, each returning a path
  or None. Callers pass them through `filter_list(preview=...)`; `picker.py` is unchanged.
- Nothing happens unless the terminal draws images: `filter_list` drops `preview` before calling it otherwise, and
  callers build nothing up front. Every lookup (inventory index, theme commit, archive unpack, download) runs lazily
  inside the `previews.py` call for a highlighted row, and is memoized there.
- Which scrape files exist comes from `inventory` (the storage cache), indexed with `scrape_plan.scrape_index`, never
  by listing storage.
- Fetching is blocking, on hover. With a storage folder or the mirror (`s3.read_root()`), the file is shown in place.
  With a bucket it is downloaded once with `s3.download` into `~/.sync-roms/previews/<key>` and reused.
- Theme outlines: the first time a system row needs one, the archive (`themeart.ESDE_ARCHIVE`) is streamed once and only
  `artwork-outline/*.png` is kept, in `~/.sync-roms/theme-art/<commit>/`; an older commit's folder is removed. The
  commit comes from `themeart._stored_commit()`. No archive in storage: no outlines.

## Approaches

- **Blocking fetch on hover (picked):** simplest; storage is a NAS folder, so there is nothing to wait for except the
  one-time outline unpack.
- Background fetch with poll redraw: never blocks, but adds threads for a wait that only S3 has.
- Pre-fetching a list's images when it opens: thousands of files, most never looked at.

## Non-goals

No video, no other media types, no cache pruning for `previews/`.

## Left to the builder

Exact wiring per caller; tests for `previews.py` lookups (order, missing files, folder vs. bucket, outline cache by
commit).

# `saves manage`: inspect, label, move, prune and delete stashes

## Why

`saves stash` only adds stashes and `saves apply` only reads them, so the stash folder
(`~/.sync-roms/saves/<system>/<game>/<YYYYMMDD-HHMMSS>-<card>/`) grows forever and the only cleanup is deleting
folders by hand. The user wants one place to look through every stash and do whatever tidying they need: see what a
stash holds, tell same-game stashes apart, fix one filed under the wrong system, thin out old ones, and delete
the ones they don't need.

## Goals

- `sync-roms saves manage`: one interactive screen listing every stash, with these actions:
  - **inspect** a stash's files;
  - **label** a stash (a short note, e.g. "before final boss");
  - **move** a stash to another system (never another game);
  - **prune**: keep the newest N per game, the rest picked for deletion;
  - **delete** picked stashes.
- `saves apply` shows a stash's label, so same-game stashes can be told apart there.

## Non-goals

- No scriptable subcommands (`saves list`, `saves rm`, ...) and no `--json` (approach B/C, not picked).
- No card involved: `manage` works on the data folder only, takes no CARD argument and no `--retroarch`.
- No editing of a stash's individual files (removing one file from a stash, adding files).
- No merging of stashes.

## Anti-goals

- Deleting anything not picked and confirmed, or anything outside `stash_root()`.
- Losing a label or a stash on a move (a move that collides must not overwrite another stash).

## Approaches

- **A. One interactive screen, `saves manage`** (picked): the shared picker (`picker.filter_list`) lists stashes as
  rows with columns; hotkeys act. Matches the card/set editors, filtering and multi-select come free.
- B. Scriptable subcommands (`saves list/rm/note/move/prune`): scriptable, but a stash must be named by path or an
  id, clumsy for a hands-on cleanup.
- C. A plus `saves list [--json]`: more code for a listing nobody asked for.

The user picked A.

## Design

### Command

`sync-roms saves manage [--dry-run] [--yes]`, a third `saves` subcommand next to `stash` and `apply` (parser in
`commands.build_parser`, `commands.second_words`, `cli.SUBCOMMANDS`/`cli.TOPICS` help, README). It needs a terminal
(`ui.require_terminal`). With no stashes it prints a yellow "No stashed saves in <stash_root>" and exits 0. The code
lives in `saves.py` (`manage_command`), next to `stash_command`/`apply_command`.

### The list

One row per stash folder under `stash_root()`, sorted like `load_stashes()` (game, then system, then newest first).

- Label: the game, plus ` · <rel>` for a Pickles stash (as `apply` does).
- Columns: system name (dim), `from <card>`, stashed date (`YYYY-MM-DD HH:MM`, dim), file counts (`_counts`), total
  size (`ui.human_size`), core (cyan), `N missing` (red) when files listed in `stash.json` aren't in the folder, and
  the stash's label.
- **Unreadable stashes** (a `stash.json` that `load_stashes()` rejects, or a folder under a game folder with files but
  no `stash.json`) are listed too, label = the folder's path relative to `stash_root()`, marked `unreadable` (red).
  They can only be inspected (their files) and deleted; label, move and prune skip them. `load_stashes()` itself keeps
  skipping them, so `apply` is unchanged.

### Keys

The list is multi-select (Space/Tab toggle, `a` all/none shown, `/` filter, as every picker). Actions act on the
toggled rows, or on the highlighted row when none are toggled.

- **Enter: inspect.** Opens a second list of the stash's files: name (with `<rel>/` for Pickles), kind, size, mtime,
  `missing` (red) for a listed file that's gone, `extra` (dim) for a file in the folder that `stash.json` doesn't
  list. Esc goes back to the stash list, cursor where it was.
- **w: label.** The picker's own note line (`on_note`/`note_text`), prefilled with the current label. Saved at once
  as `"note"` in that stash's `stash.json` (`store.write_json`, `store.PRETTY`); an empty line removes the key.
- **m: move to another system.** Asks for the system (a `filter_list` of `systems.json`'s systems, current one
  highlighted). The game never changes (the user's call: a stash's game isn't renamed, so its files keep their names).
  A stash already in that system is left alone. Otherwise its folder moves to
  `<stash_root>/<system>/<game>/<its own folder name>` (a `-2`, `-3`... suffix when taken, as `write_stash` does) and
  `stash.json`'s `system` is rewritten; label and everything else stay. A Pickles (muOS) stash also gets each file's
  `rel` first part switched to the new system's `folders["muos"]`, so `apply` puts it in that system's ROM folder; a
  system with no muOS folder is refused for it with a note. With several stashes toggled, all move to the picked
  system.
- **p: prune.** Asks how many to keep per game (`ui.ask`, default 1, a positive whole number). Then every readable
  stash beyond the newest N of its (system, game, Pickles rel) is toggled on and every other row off, with a note
  saying how many were picked. Nothing is deleted: the user reviews the picks and presses `d`.
- **d: delete.** Lists the stashes about to go (game, system, date, label) and asks `ui.confirm(..., default=False)`
  ("Delete N stash(es)? This can't be undone."). On yes each stash folder is removed (`shutil.rmtree`), then its game
  and system folders if they're now empty. With `--yes` the question is skipped. Rows deleted leave the list; the list
  stays open.
- **Esc / q** leaves. Everything was saved as it happened, so there's nothing to review or discard at the end. A
  closing line says what was done (e.g. "🗑️ Deleted 3 stash(es), moved 1, labelled 2").

### Safety

- Every path acted on must resolve inside `stash_root()` (`os.path.realpath` check); anything else is refused.
- `--dry-run`: the screen works the same, but label, move and delete print what they would do (dim) and change
  nothing; the closing line says "Would ...".
- Filesystem errors (`OSError`) on one stash are warned about and that stash is skipped; the rest go on.

### `saves apply`

Its stash list gains the label as a last column (dim), empty when the stash has none.

## Left to the builder

- How the screen loops (re-entering `filter_list` with `session` and `cursor` after each hotkey, as `pick_apply`
  does), and how notes are queued (`picker.queue_note`).
- Exact column order and wording of notes and messages, within the style of `stash`/`apply`.
- Tests in `tests/test_saves.py` (or a new `tests/test_saves_manage.py`, importing `helpers`): listing incl.
  unreadable and missing-file stashes, label write/remove, move incl. collision suffix and a muOS stash's `rel`, prune
  picks, delete incl. empty-parent cleanup and the stays-inside-`stash_root` check, dry-run writes nothing, `apply`
  shows the label. The README table test must pass.

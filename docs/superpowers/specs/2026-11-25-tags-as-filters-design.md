# Tags as filters: complete tags, sticky filter, editor UX

## Intent
Tags replaced sets. A set was a destination you opened; a tag is a filter you apply while doing something else (picking games, adding to a collection, browsing). Two things from the sets era no longer fit: tags are thin (4,157 of 10,750 tagged games carry one tag), and tag filtering exists only in some editor lists.

## Goals
1. Every version of a game carries every tag that applies. Filtering by "Mario" or "Shmups" shows all of them, on every system.
2. A tag filter, once set, stays on across every games list in every editor until cleared, and is always visible.
3. Editor UX is consistent and filter-first, from an audit the user approves item by item.
4. CLAUDE.md rules from the sets era are replaced.

## Non-goals / anti-goals
- Tags never put a game on a card (unchanged).
- No tag groups or hierarchy (tags stay flat).
- No agent writes to storage's `tags.json` directly; nothing applied without the user seeing a per-tag diff summary.
- Not a rewrite of the editors: audit findings are done only when approved.

## Constraints
- Storage access only through `tags.py`/`shared.py` (bucket or folder). No backup/test files in storage.
- Python via `uv`; tests must pass on 3.12+; `tests/test_readme.py` and others check data shapes.
- Conventional commits; release-please owns versions.

## Approaches considered
- Data review: per-system agents (A), per-tag agents (B), both (C). **Chosen: C**: per-system agents propose all applicable tags using the full vocabulary (large systems chunked), then per-tag precision/recall agents recheck the big or suspicious tags.
- Filter: sticky across views (chosen, changeable later) vs per list.

## Design

### 1. Rules (CLAUDE.md)
Remove "A game is tagged once across all tags" (one version per game, original over ports) and the rule that later versions go in `variants` instead of getting tags; remove the "one-version pool" wording in `tags suggest`/`check` descriptions and the Retro Oddities/Handheld/System Essentials "own versions" exception. New rule: every version of a game gets every tag that applies; a game with no fitting tag is simply untagged. `variants` stays as the "related versions on other systems" feature (`v` key) and is no longer a tagging device. Code that assumes one version per game (`tags suggest` pool, `check`'s untagged count, `update-variants` skill, `tools/`) is updated to match.

### 2. Data review (subagent workflow, scratch files only)
- Export per-system game lists (title via `names.title`, storage key, current tags) and the tag vocabulary (id, name, description) to a scratch folder.
- Phase 1, per system (big systems chunked, e.g. fbneo, nes, psx, nds, snes, gba, psp, gc, ps2, genesis): an agent proposes `{key: [tags to add]}` (and removals only for clear errors) into a proposals file.
- Phase 2, per tag: an agent per large or suspicious tag (by count change, or ones the user flags) checks precision and recall across systems.
- Merge proposals, show a per-tag summary (added/removed counts, samples), user approves, apply through `tags.change_game_tags`/`shared.update`.
- Untagged games are included. New tags are proposed, never created silently.

### 3. Sticky tag filter
One shared `TagFilter` in `tagui.py` (module-level, per run). Every games list reads it: the card editor's lists (all-games, per-system, collection), `edit.py`'s generic lists, add-from-system/tag pickers, `listedit.toggle_all`, variants, and the collection and tag editors' game lists. A banner line (`✅ … · 🚫 … (c clear)`) shows in every list while it is set. `s` opens the tag filter in every games list; `c` clears. Lists that are not games (cards, devices, settings) ignore it. Selection-affecting actions (select all, toggle all) apply to what the filter shows, and say so.

### 4. Editor UX audit
A read-only agent pass over `edit.py`, `listedit.py`, `cardedit.py`, `collectionedit.py`, `tageditor.py`, `tagui.py`, `picker.py` produces a ranked list of inconsistencies and improvements with filters in mind (key consistency, discoverability, counts, tag-from-anywhere flows, bulk tag editing from a filtered list, etc.). The user picks which to do; those become the implementation tasks.

## Order
1. Rules + code assumptions (small). 2. Sticky filter everywhere. 3. Audit, user picks, implement. 4. Data review runs in parallel with 2 and 3 (it touches data, not code), applied last after approval.

## Left to the builder
Exact key bindings where `s` conflicts, chunk sizes, agent prompts, how the sticky state is exposed to `picker.filter_list`, test layout.

## Calls made (from the builder check; the author's, not agreed with the user)
- Existing `variants` entries stay untouched; variant versions get no new `games` records. Variants remain a "related versions" note, not a tagging device.
- The filter narrows display and bulk actions: select-all, toggle-all and tag removal act only on shown games, with the count in the prompt. Single-game actions are unaffected.
- One process-wide singleton, never auto-cleared. A list with no matches shows the banner and "no games match".
- After `t` changes a game's tags, it stays until the list next refreshes, then drops out if no longer matching; the cursor keeps its position.
- The card editor's `s` becomes the sticky tag filter picker (it replaces "all games narrowed by tags first"); README, help and tests update. `tageditor` lists its tags, not games, so it ignores the filter.
- Plan covers rules + sticky filter fully; audit implementation waits for the user's picks; applying data-review results is a manual gate.
- Data review covers every system that has games in storage, no budget cap; big systems chunked.
- `check` replaces the per-system untagged list with one count per system; `tags suggest` pools every version.

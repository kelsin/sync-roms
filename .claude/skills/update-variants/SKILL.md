---
name: update-variants
description: Use when new ROMs were uploaded to storage and the sets' game variants need updating, or when asked to find, add or clean up variants of set games (enhanced ports, remasters, translations of games already in a set).
---

# Update variants

A set game's `variants` (see "Data files" in CLAUDE.md) list other versions of the same game that add something.
This skill finds new ROMs in storage that are variants of set games and adds them, after the user approves.

**It only edits `variants`.** It never adds, removes or swaps set entries, and never changes which version a set
uses: the user edits sets by hand. When a new ROM looks like a better main version than the set's entry, say so in
the report and leave the set alone.

Run every command from the repo root.

## 1. Find candidates

```bash
sync-roms cache update
uv run --frozen python .claude/skills/update-variants/scripts/find_candidates.py > <scratchpad>/candidates.json
```

The output has:
- `matches`: set games (`game`, `title`, `system`, `sets`, existing `variants`) with `candidates`, ROMs no set lists
  (as an entry, extra file or variant) whose title or arcade clone family matches. A multi-disc candidate's discs
  are in its `files`.
- `stale`: variants whose ROM is no longer in storage.
- `unmatched`: how many new ROMs matched no set game. They are not judged or recorded; mention the count.
- `checked_file`: `~/.sync-roms/variants-checked.json`, the ROMs already judged; they are never offered again.

No matches and no stale variants: tell the user there is nothing to update and stop.

## 2. Judge each candidate

Judge per ROM: one ROM often matches several set games (an arcade game and its many ports). Pick the set game it is
the same game as; it is a variant of that one game at most, and gets one verdict. Count and report ROMs, not pairs.

A candidate is a **variant** only when it is the same game as the set entry and adds something: new content, modes
or characters, a remaster or HD version, an enhanced port, an English translation of a Japanese-only game. Anything
else is **not a variant**, with a short reason:

| Candidate | Verdict |
|---|---|
| Same game, nothing added (straight port, re-release, regional copy, revision, Classic NES Series, Neo Geo CD copy) | not a variant: "same game, adds nothing" |
| Plays substantially differently (other developer or design, demake, new-engine remake like Pokemon FireRed) | not a variant: "different game" |
| Only shares the title | not a variant: "different game" |
| Would win as the main version under the CLAUDE.md order (arcade original over a port, the lead platform, English for a text-heavy game) | not a variant; report it |
| Can't tell from its name and what you know | leave it out of the decisions; list it for the user |

A variant's note starts with the system's common name and a colon, says what it adds in plain words, under 80
characters: `DS: adds the Lost Sanctum, a bonus dungeon and a new ending`.

More than about 40 candidates: split them into batches of about 100 and give each to a subagent with this section
and the CLAUDE.md rules; collect their verdicts as the decisions file below.

## 3. Show the proposal and wait

Show the user one table of the proposed variants (set game, new variant, note), the stale variants to remove, the
number of ROMs judged not variants with a few examples, the ROMs you couldn't judge, and the unmatched count. Report
any "better main version" findings separately. Write nothing until the user approves, even when no variant is
proposed (approval then records the judged ROMs as checked); apply their corrections.

## 4. Apply

Write the approved decisions to `<scratchpad>/decisions.json`:

```json
{"add": [{"game": "<set entry bucket>", "bucket": "<variant bucket>", "note": "...", "files": ["<disc>", "..."]}],
 "remove": [{"game": "<set entry bucket>", "bucket": "<stale variant bucket>"}],
 "checked": {"<candidate bucket>": "<why it is not a variant>"}}
```

```bash
uv run --frozen python .claude/skills/update-variants/scripts/apply_variants.py <scratchpad>/decisions.json
uv run --frozen python -m unittest tests.test_set_data
```

The apply script adds each variant to the game in every set that lists it and records every judged ROM as checked.
Rejected candidates go in `checked` so later runs skip them; candidates the user wants to decide later are left out.
Show `git diff --stat` and commit only when asked (Conventional Commits, e.g. `feat(sets): add variants for new uploads`).

`find_candidates.py --baseline` marks every ROM no set lists as checked without judging it. Use it only when the user
asks to skip the backlog.

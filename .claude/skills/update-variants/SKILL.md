---
name: update-variants
description: Use when new ROMs were uploaded to storage and the tagged games' variants need updating, or when asked to find, add or clean up variants of tagged games (enhanced ports, remasters, translations of games already in tags.json).
---

# Update variants

Variants live on the game records of storage's `tags.json` (see "Data files" in CLAUDE.md): a record's `variants`
are notes on related versions of the same game that add something. This skill finds new ROMs in storage that are
variants of tagged games (games with a record) and adds those notes, after the user approves. The scripts read and
write `tags.json` in storage, never in the repo.

**It only edits `variants`.** It never adds, removes or retags game records. Every version of a game is tagged on its
own, variant or not: the user tags them with `sync-roms tags edit` or `sync-roms tags suggest`, never this skill.

Run every command from the repo root.

## 1. Find candidates

```bash
uv run sync-roms cache update
uv run --frozen python .claude/skills/update-variants/scripts/find_candidates.py > <scratchpad>/candidates.json
```

The output has:
- `matches`: tagged games (`game`, `title`, `system`, `tags`, existing `variants`) with `candidates`, ROMs
  whose title or arcade clone family matches and that are not a file or variant of any record. A ROM tagged on its own (a
  record key) is still offered for another game it is a version of, never for itself, its own files or a game that
  already lists it as a variant. A multi-disc candidate's discs
  are in its `files`.
- `stale`: variants whose ROM is no longer in storage.
- `unmatched`: how many new ROMs matched no tagged game. They are not judged or recorded; mention the count.
- `checked_file`: storage's `variants-checked.json`, the ROMs already judged; they are never offered again.

No matches and no stale variants: tell the user there is nothing to update and stop.

## 2. Judge each candidate

Judge per ROM: one ROM often matches several tagged games (an arcade game and its many ports). Pick the tagged game
it is the same game as; it is a variant of that one game at most, and gets one verdict. Count and report ROMs, not pairs.

A candidate is a **variant** only when it is the same game as the tagged game and adds something: new content, modes
or characters, a remaster or HD version, an enhanced port, an English translation of a Japanese-only game. Anything
else is **not a variant**, with a short reason:

| Candidate | Verdict |
|---|---|
| Same game, nothing added (straight port, re-release, regional copy, revision, Classic NES Series, Neo Geo CD copy) | not a variant: "same game, adds nothing" |
| Plays substantially differently (other developer or design, demake, new-engine remake like Pokemon FireRed) | not a variant: "different game" |
| Only shares the title | not a variant: "different game" |
| Can't tell from its name and what you know | leave it out of the decisions; list it for the user |

A variant's note starts with the system's common name and a colon, says what it adds in plain words, under 80
characters: `DS: adds the Lost Sanctum, a bonus dungeon and a new ending`.

More than about 40 candidates: split them into batches of about 100 and give each to a subagent with this section
and the CLAUDE.md rules; collect their verdicts as the decisions file below.

## 3. Show the proposal and wait

Show the user one table of the proposed variants (tagged game, new variant, note), the stale variants to remove, the
number of ROMs judged not variants with a few examples, the ROMs you couldn't judge, and the unmatched count. Write
nothing until the user approves, even when no variant is proposed (approval then records the judged ROMs as checked);
apply their corrections.

## 4. Apply

Write the approved decisions to `<scratchpad>/decisions.json`:

```json
{"add": [{"game": "<tagged game bucket>", "bucket": "<variant bucket>", "note": "...", "files": ["<disc>", "..."]}],
 "remove": [{"game": "<tagged game bucket>", "bucket": "<stale variant bucket>"}],
 "checked": {"<candidate bucket>": "<why it is not a variant>"}}
```

```bash
uv run --frozen python .claude/skills/update-variants/scripts/apply_variants.py <scratchpad>/decisions.json
uv run sync-roms check
```

The apply script adds and removes the variants on the games' records in `tags.json` in one write, made to a fresh
copy of the storage file, so variants and records another machine changed meanwhile are kept. A game whose record is
gone by then is skipped and listed ("No tags.json record, skipped"), never recreated, and its proposed variants aren't
recorded as checked. It records every other judged ROM as checked, and changes nothing when the storage folder isn't
mounted. Rejected candidates go in `checked` so later runs skip them; candidates the user wants to decide later are
left out. There is nothing to commit: report the games it changed (the last line of its output), any skipped games
and any problems `sync-roms check` shows.

`find_candidates.py --baseline` marks every ROM that is no record's file or variant as checked without judging it. Use it only when the user
asks to skip the backlog.

Tagged ROMs are candidates too, so the tagged records not yet in `variants-checked.json` come up once, a one-time backlog: judge them as any others.

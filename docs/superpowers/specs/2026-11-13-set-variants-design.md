# Set game variants

## Intent

Sets now hold one version of each game. A later version of the same game that adds something (Chrono Trigger DS over
SNES, Wind Waker HD, Kirby Super Star Ultra) is listed in that game's `variants` in the set file:

```json
{"title": "Chrono Trigger", "system": "snes", "bucket": "snes/Chrono Trigger (USA).zip",
 "variants": [{"bucket": "nds/Chrono Trigger (USA).zip", "note": "DS: adds the Lost Sanctum, a bonus dungeon and a new ending"}]}
```

The editors should show a game's variants when it is highlighted, and the card editor should let the user add one with
a key. Syncing a whole set still syncs only its main entries.

## Goals

- One index of variants across all sets: canonical bucket → its variants, variant bucket → its canonical game.
- The picker can show a per-row note on the bottom line for the highlighted row (same slot as the locked-row note).
- Card editor, system view: a game with variants shows `↳ Variant: <note> (v adds it)`, or `✅ on the card` once
  added; `v` toggles the variant on the card, saved under the variant's own system (often not the system on screen).
  Several variants: `v` opens a small list. A row that is itself a variant shows `Variant of <system> — <title>`.
- Set editor, collection editor and add-from-set lists show the same note, read-only (no `v`).
- `test_set_data` checks variants: known system prefix, not also an entry of the same set, non-empty note.

## Non-goals

- Editing variants in the set editor (they are written by hand in the JSON).
- Syncing variants with whole sets, or counting them in the budget before they are added.
- Variant rows inside the lists (they would break the one-system-per-view lists).

## Approaches

- **Bottom-line note plus a `v` key (picked):** fits the existing locked-note slot and the per-system card view; the
  only new write path is adding a game to another system of the card.
- Variants as extra indented rows: mixes systems in a per-system list. Rejected.
- Note only: can't add the variant, which was asked for. Rejected.

## Left to the builder

Exact wording of the hint line, where the index lives in `store`, and how the card editor merges the other-system
picks into the card on save (it must keep the card's other systems, sets and excluded lists intact).

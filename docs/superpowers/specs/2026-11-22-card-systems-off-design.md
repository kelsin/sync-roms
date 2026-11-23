# Turning systems and collection games off on a card

## Why

A device can run a system you rarely play on it, and a collection can bring games you don't want there, for space or
taste. Today a collection syncs whole (its games are locked in the card editor and `excluded` never applies to them),
and the only way to keep a system off one card is the per-device overlay, which hits every card of that device and
hides the system from the editor.

## Goals

- Untick single collection games on a card.
- Turn a whole system off on a card while its device still runs it: nothing of that system syncs to that card.
- Turning the system back on restores what it had: picks, full system, sets, collections all stay saved.

Non-goals: per-device changes, a global switch, changes to the collection editor or to collections themselves.

## Approaches

- **A (picked): reuse `excluded`, add `systems_off`.** Collection games honour the card's existing `excluded`; a new
  card field lists the systems that are off. One exclusion list for "this game isn't on this card", wherever it comes
  from.
- B: a separate `collection_excluded` list. More fields to carry through `cardshare`, `budget`, `bbs` and the schema,
  and a game in both a set and a collection would need unticking twice.
- Device overlay: rejected, per device rather than per card, and it hides the system.

## Design

**Collection games.** `excluded` drops a collection game from the card, as it does a set game. Surprise games stay
locked (replaced through Surprise, as now). A full system still ignores `excluded`.
- `store.load_manifest`: apply the card's exclusions after `merge_locked` too (collection games), not only to merged
  set/pick lists. Surprise picks are not filtered.
- `budget._system_keys`: collection games minus `excluded`.
- Card editor (`cardpicks.SystemPicks`): a collection row is no longer locked: off adds its key (and its multi-disc
  group) to `excluded`, on takes it out. Surprise rows stay locked. The row keeps its "from 💖 <collection>" label.
  `_locked_note` only for surprise rows.

**Systems off.** New card field `systems_off`: sorted system ids, absent when empty.
- `store.load_manifest` (one card): each off system gets `games = []` and no `full_system`, after everything else is
  merged. Sync then treats it as a system with nothing listed, so its ROMs on the card are offered for deletion as
  today (kept with `--no-delete`). `games`, `excluded`, `collections` in cards.json are untouched.
- Surprise never picks from an off system (`surprise._current` adds `systems_off` to its excluded set), and an
  existing surprise there is dropped from the card's current picks like one on an excluded system. This includes a
  surprise kept in `run_surprise`'s keep/replace question whose system is then turned off in the card editor:
  `fill_surprises` (after the editor, before copying) drops it through `_current` and picks a new game for that slot
  from the systems still on. A test covers that sequence.
- `budget`: an off system's usage is 0.
- Card editor systems list: `x` toggles the system under the cursor off/on, saved at once (like `f`), row marked
  `🚫 off` and its size 0. Entering an off system still opens its games (picks can be edited), with a line saying the
  system is off on this card. Listed in `LIST_HINT`/`LIST_KEYS`.
- `D` (clear all) leaves `systems_off` alone.

**Data and docs.** `cards.schema.json` gets `systems_off`; CLAUDE.md's card fields table gets the row and the
`excluded` row drops "never applies to collections"; README if it documents the editor keys.

## Left to the builder

- `cardshare` doesn't copy `systems_off` (it's about this card's device). Builder's call to confirm.
- Exact wording of the row mark and the off notice.
- Tests: manifest with an off system and with an excluded collection game, budget, surprise skipping, cardpicks
  toggling a collection row, the `x` hotkey.

# Translated scrapes

## Intent

A fan translation is scraped as its original game (ScreenScraper's media and metadata), so the frontends show it
under the same title as the untranslated ROM. Translated ROMs should keep that game's media but get the title
"<ScreenScraper's name> - Translated", so they can be told apart in ES-DE, Knulli and the rest.

## Goals

- A ROM is translated when its file name has a translation tag, or when the user marks it.
- Its `scrapes/<system>/metadata.json` entry gets `"translated": true` and `name` set to ScreenScraper's name plus
  ` - Translated`. Everything else (media, desc, genre...) is the original game's.
- `scrape review` gets a `[t]ranslated` answer: search like `[s]`, then scrape the pick as a translation.
- `scrape match SYSTEM ROM GAME --translated` scrapes the ROM as a translation of GAME. If the ROM is in
  `ignored.json`, it is taken off that list first (so ignored translations can be brought back in one step).
- The ~120 entries already scraped from tagged ROMs get the flag and title once, with no ScreenScraper requests.

## Non-goals / anti-goals

- The base title is always ScreenScraper's name, never the English title from the file name.
- No personal list of marks: the mark lives in the shared metadata entry only.
- Never add the suffix twice, and never mark a ROM whose name only looks like a tag (`Klax (USA, Europe) (Tengen)`,
  `Just in Time Translations - Say It in 6 Languages`).

## Approaches

- **A (picked):** flag and title in the shared `metadata.json` entry, plus file-name tag detection. Survives
  re-scrapes from any machine; titles in storage match what frontends show.
- B: marks in a personal `~/.sync-roms/` file. Simpler, but lost when another machine re-scrapes.
- C: marks only, no tag detection. Leaves ~120 existing translations to mark by hand.

## Design

**Tag detection** (`screenscraper` or a small helper beside `scrape_review.search_name`): a case-insensitive match
on the file name for any of `(T)`, `[T]`, `(T-En...)`/`[T-En...]`/`[T+Eng...]`, `(English v...)`, and a
parenthesised or bracketed tag containing `Translation` (`(English Fan Translation)`, `(RCG Translation, Switch)`).
Only whole tags count, so `(Tengen)` and a title word "Translations" don't.

**Writing an entry:** wherever a `done` result becomes a metadata entry, the entry is translated when the file name
is tagged, the user asked (`--translated` / `[t]`), or the entry being replaced already had `"translated": true`.
Then `translated` is set and ` - Translated` appended to `name` unless it already ends with it.

**Review:** `PROMPT` gains `[t]ranslated`; it runs the same search as `[s]` and passes the translated flag through to
`match_command`.

**Match:** `--translated` on `scrape match` (and the old `--scrape-match` form). An ignored ROM is removed from
storage's `ignored.json` (new `ignore.remove`, mirroring `ignore.add`) before scraping; without `--translated` an
ignored ROM behaves as today.

**Existing entries:** a one-off script in `tools/` (my call: not a command, since the data is shared and needs it
once) reads each system's `metadata.json` from storage, applies the rule above to tagged ROMs, and writes back the
changed files. The user runs it once, after a dry run listing the changes.

## Left to the builder

- Exact regex and where the helper lives; tests for the tag cases above, including the two false hits.
- Help text for `--translated` and the review prompt.

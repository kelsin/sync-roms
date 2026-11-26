# Collection export and import

## Intent

Let someone who shares your storage and runs sync-roms take one of your collections from the Tailscale share page
and make it their own collection. Each import is a one-time copy: after it lands, it is theirs, with no link back.

## Goals

- An **Export** button for each collection on the share page (`collections page` / `collections share`, which has
  file paths). It downloads `<id>.json`.
- `sync-roms collections import FILE...` adds those files to `~/.sync-roms/collections/`.
- When the collection's id is already taken: list the differences, then **Merge / Replace / Rename / Skip**.

## Non-goals

- No button on the public page (`collections publish`, `page_data(public=True)`).
- No tracking of where a collection came from and no update on re-import.
- No mapping between different storages: bucket keys are used as they are.

## Approaches

- **A. Download a file (picked).** The page downloads the collection's own file format, and the CLI imports it.
  This works like `cards export`/`import`, and nothing new runs on the network.
- B. Copy the JSON to the clipboard and import it from the clipboard or stdin. Clipboard access depends on the
  platform, and it's easy to paste the wrong thing.
- C. Import from the page's link by fetching the page. This needs the share server running and ties the CLI to the
  page's HTML format.

## Design

**Page.** `page_data(public=False)` adds an `export` field to each collection: exactly `collections._file_data(c)`
(name, description, art, games with system, bucket, files, title and note). `page.js` shows an Export button for each
collection only when `export` is present. The button makes a JSON Blob and downloads it through `<a download="<id>.json">`.
That also works when the page is opened from `file://`.

**Import.** `collections import FILE... [--dry-run] [--yes]`, a new `collections` subparser that follows the CLI
rules (`commands.build_parser`, `cli.TOPICS`, `cli.SUBCOMMANDS`, `second_words`, README Commands table).

- Read and validate each file the way `load_collections` does: a text `name`, a `games` list, and games cleaned with
  `_clean_games`. A bad file is warned about and skipped.
- The id is `store.slug(name)`, never the file name (browsers rename duplicate downloads to `foo (1).json`). A name
  `collection_problem` rejects for a reason other than an id clash (empty, Surprise) is skipped with that reason.
- When the id is free, the collection is saved with `save_collection`.
- When the id is taken, sync-roms prints the differences, matched by bucket: the games only in the file (titles,
  grouped by system) and the games only in yours (a count plus titles). Then it asks:
  - **Merge** (default): your collection gets the file's games it doesn't have, appended. Your name, description,
    art and notes stay.
  - **Replace**: the file's collection is saved under the same id, and the old file is kept as `<id>.json.bak`
    (`store.backup`). Cards that use the id keep using it.
  - **Rename**: asks for a new name until `collection_problem` accepts it, then saves under that name's id.
  - **Skip**.
  - If nothing differs, it says so and skips without asking.
- `--yes` answers Merge. With a clash, no terminal and no `--yes`, the file is skipped with a warning. `--dry-run`
  prints what each file would do and writes nothing.
- Each file ends with one line: `💾 Imported <name>`, `🔀 Merged N games into <name>`, `Replaced <name>`, or `↩️ Skipped <name>`.

## My calls (correct if wrong)

- Merge is the default, and the answer `--yes` gives, because it never loses anything.
- Games aren't checked against storage. You share the storage, and a stale cache would give false alarms.
- Art ids are repo data, so the same for everyone, and are kept as they are.

## Left to the builder

The exact wording and layout of the differences list and the prompt (use the existing `ui` helpers), where the
button sits in the collection's header, and the tests: page data with and without `public`, the JS button present
only with `export`, each import branch, the slug-from-name rule, `--dry-run` and `--yes`. The README section next to
`collections page` and the CLAUDE.md collections-page line get a sentence each.

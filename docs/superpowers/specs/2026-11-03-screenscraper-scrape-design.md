# Scrape from ScreenScraper on the computer

## Intent

Scraping media on a handheld is slow: the card has to be pulled and put back to upload it, and the device's WiFi chip is slower than the computer's. Instead, the user's computer scrapes directly from ScreenScraper using the user's own account and writes the results to the bucket's `scrapes/` folder. Sync already installs from `scrapes/` onto cards, so nothing about syncing changes.

## Goals

- A command, run on the computer, that reports which available ROMs have no scrape metadata and scrapes them from ScreenScraper into `scrapes/<system>/`.
- A manual path: for a ROM the automatic lookup can't match, the user looks the game up on screenscraper.fr and supplies a game ID (or a name to search), and that ROM is scraped from that game.
- The user's ScreenScraper username and password are stored in `~/.sync-roms/settings.json`.

## Non-goals

- Changing how sync installs scrapes, or any layout.
- Re-scraping or modifying ROMs that already have metadata.
- Downloading whole ROMs from S3 just to hash them. Hashing reads files in place only when the storage is a folder (`root`, e.g. a mounted network share); on S3, unmatched ROMs are reported, not downloaded.
- Support for scrapers other than ScreenScraper.

## Anti-goals

- Credentials ending up in the repo, the bucket, logs or output. (Existing upload already excludes ScreenScraper credentials from `es_settings.xml`; keep it that way.)
- A half-finished run losing work: quota or network failure must leave everything uploaded so far valid, and a re-run must continue where it stopped.

## Constraints

- Same bucket layout and profile rules as the rest of the tool: reads use the read profile, uploads use the write profile; confirm before anything that overwrites.
- Output uses the existing `scrapes/` formats: `scrapes/<system>/metadata.json` (neutral JSON, fields from `scrape_plan.TEXT_FIELDS` plus `rating` and `releasedate`), media under `scrapes/<system>/<type>/<ROM name>.<ext>` using the ES-DE media type folder names in `scrape_plan.MEDIA_TYPES`, and the derived `onion/` and `slot/` PNGs made the way `--upload-scrapes` already does.
- Repo files must not contain notes about the bucket's contents. Personal data lives in `~/.sync-roms/`, never in the repo.
- Conventional commits; follow the existing CLI structure in `cli.py` (subcommand plus legacy flag mapping, `--dry-run`).

## Decisions made

- **Settings file permissions.** `settings.json` holds the ScreenScraper username and password. Every time it is read, if its mode is not 600, set it to 600. It is created as 600 on write (today `save_setting` writes with the default umask).
- **Which ROMs.** Candidates are the available ROMs (same set `scrape_files.bucket_roms` already computes: the games a sync would install) that have no entry in the system's `metadata.json`. The command first reports these.
- **Two storage backends.** The tool can use an S3 bucket or a folder (`root` setting / `ROMS_ROOT`, e.g. a mounted network share), which replaces S3 entirely with the same layout (`s3.py` abstracts both). The scraper works against either and writes to `scrapes/` through the existing backend functions.
- **Matching, in order, with a folder (`root`).** (1) Hash the ROM file in place (MD5, SHA1, CRC32 as ScreenScraper needs) and look it up by hash. (2) Fall back to file name plus size. (3) Otherwise unmatched: reported. Computed hashes are cached in `~/.sync-roms/` keyed by path, size and mtime so re-runs and large files aren't re-read. (The folder backend's listing ETag is a fake `mtime-size` value, never an MD5; don't use it for matching.)
- **Matching, in order, with S3.** (1) MD5 from the listing's ETag, only when it has no `-` (a multipart ETag is not an MD5; see `diff.py`). (2) File name plus size. (3) Otherwise unmatched: reported, never downloaded.
- **Hash validity to verify.** Whether ScreenScraper matches the hash of a zip or recompressed CHD the way the user stores it (versus the original dump) must be checked against its documentation. ROMs whose stored form doesn't match fall to name matching or the manual path.
- **Manual matches.** The user supplies a ScreenScraper game ID, or a name which is searched and the candidates shown for the user to pick. Each ROM-to-game-ID match is saved in `~/.sync-roms/` (personal data) and reused on later runs.
- **Media.** All media types ScreenScraper has that map to the ES-DE type folders in `MEDIA_TYPES` are fetched. Each type can be turned off.
- **Quota.** ScreenScraper limits an account's parallel threads and daily requests. The command reads the limits from the API response, stays within them, and stops cleanly when the daily quota is hit; a re-run continues.

## Conventions and builder's calls (from review)

- **Keys.** Follow what `--upload-scrapes` and sync already use: `metadata.json` is keyed by ROM path including extension (as `scrape_plan.parse_gamelist` produces and `bucket_roms` returns), media files are named by ROM path without extension (`rom_stems`). Candidates are `bucket_roms` paths with no `metadata.json` key.
- **Derived images.** Onion and Slot images are made from the freshly downloaded art in a local temp folder by reusing the existing derivation code; a minimal refactor of `scrape_files` to share it is fine as long as `--upload-scrapes` behaves the same. (Builder's call.)
- **Crash safety.** Upload a ROM's media first and its `metadata.json` entry last, so an entry means the ROM is complete. Rewrite `metadata.json` in batches and merge with the bucket copy each time. One confirmation per run covers the metadata overwrite; `--dry-run` lists it. (Builder's call.)
- **Negative results.** ROMs ScreenScraper doesn't know are recorded in a local ledger in `~/.sync-roms/` and skipped on later runs unless the user asks to retry, so they don't burn quota. (Builder's call.)
- **Partial media.** A ROM whose entry exists but is missing media types is not re-scraped by default; a flag to fill gaps is optional. (Builder's call.)
- **Type switches** default to all on, configured in settings or flags. (Builder's call.)

- **Name-plus-size matches are trusted** (user's decision): scraped without confirmation, and counted separately in the report so they can be reviewed.

## Left to the builder

- Subcommand name and flags (e.g. under `sync-roms scrape ...`), how a manual match is entered on the command line, and the saved-match file name and format.
- Mapping ScreenScraper media types and regions to the ES-DE type folders, region/language preference for text and art, and mapping its fields to the metadata fields.
- Retry/backoff, parallelism within ScreenScraper's allowed threads, and the dev credentials ScreenScraper requires for API clients.
- How the type switches are configured (flags or settings).

## Open calls (builder's guess; flagged for review)

- Developer credentials (devid/devpassword/softname): the user has only a ScreenScraper account login. As far as I know the API also needs software developer credentials, which ScreenScraper issues on request; verify in their docs. If needed, the user requests them and enters them in settings (mode 600 like the account login); they are never put in the repo. The plan must start with this check, since it blocks the first real API call.
- The ScreenScraper API details here (hash and file-name-plus-size lookups, quota fields) come from general knowledge and must be checked against their current documentation before building.

# sync-roms

Tooling for syncing ROMs to and from the `roms.valefor.com` S3 bucket (region `us-east-1`).

## AWS profiles

Always pass `--profile` explicitly.

| Profile | Use for |
|---|---|
| `roms-readonly` | Anything that only reads: `ls`, `cp` from the bucket, `sync` from the bucket, `head-object` |
| `roms` | Anything that writes: `cp`/`sync` to the bucket, `rm`, `mv` |

Default to `roms-readonly`. Only use `roms` when a write is actually needed, and confirm with the user before any command that deletes or overwrites (`rm`, `mv`, `sync --delete`).

**Never put backup or test files in the bucket.** No `.bak` copies, scratch uploads, or test objects under `roms.valefor.com`. Keep those local.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org) for every commit and for PR titles: `<type>[scope]: <description>` (`feat`, `fix`, `refactor`, `docs`, `chore`, ...), imperative and lowercase. Merge PRs with squash so the PR title becomes the commit message on `main`.

## Bucket layout

Top-level prefixes are one per system, lowercase (`BIOS/`, `gba/`, `genesis/`, `dreamcast/`, `mame/`, `atari2600/`, ...). List them with:

```bash
aws s3 ls s3://roms.valefor.com/ --profile roms-readonly
```

## Common commands

```bash
# List a system
aws s3 ls s3://roms.valefor.com/gba/ --profile roms-readonly

# Download one file
aws s3 cp s3://roms.valefor.com/gba/game.zip . --profile roms-readonly

# Download a system (bucket -> local)
aws s3 sync s3://roms.valefor.com/gba/ ./gba/ --profile roms-readonly

# Upload (local -> bucket) -- needs write profile
aws s3 sync ./gba/ s3://roms.valefor.com/gba/ --profile roms

# Preview any write first
aws s3 sync ./gba/ s3://roms.valefor.com/gba/ --profile roms --dryrun
```

## Data files

Only one bucket layout is supported; don't add support for others. The bucket name is not hardcoded: it is the `bucket` setting in `~/.sync-roms/settings.json`, asked for on first run. BIOS files always live at `BIOS/<file>` in the bucket, so the path is derived, never stored. Whether a file exists comes from listing `BIOS/`.

BIOS lists in `systems.json` cover every emulator a system can use (default and alternate libretro cores, standalone emulators), not just the default one. These files are small, so users get all of them all the time. Don't trim a list down to the default emulator's needs. Redundant extras that no emulator needs (e.g. a dozen regional dumps of one PS1 BIOS) are not kept.

The old single `roms.json` is split by whether the data is personal. Nothing here is read from or written to the bucket.

| Where | Files | Holds |
|---|---|---|
| Repo, `data/` | `layouts.json`, `systems.json`, `devices.json` | Frontend folder layouts; systems (name, id, folder per layout, required BIOS filenames, libretro cores); device hardware (id, name, SoC, default layout). Same for everyone. |
| `~/.sync-roms/` (starters in repo `data/`) | `games.json`, `device-systems.json` | The games to sync per system (with their notes); each device's recommended systems and a short note on why. `--edit` edits the local `games.json`. A system's `games.json` entry may be `{"full_system": true}` instead of a list to sync its whole bucket folder; no default or personal list uses it. |

The repo ships starter versions of the two personal files in `data/`: `games.json` is `{}` (no games), `device-systems.json` has the default recommended systems and notes. The script copies them to `~/.sync-roms/` when missing, so each user owns their copy. Never put a real game list in the repo's `games.json`.

Repo files must not contain notes about the bucket's contents ("not in the bucket", "bucket has..."). Device notes say only why the systems were chosen, concisely.

## Notes

- Use `--dryrun` before any `sync` to the bucket; add `--delete` only when explicitly asked.
- Keep the trailing `/` on prefixes so `sync`/`ls` target the directory, not a name prefix.

"""Download ROMs and BIOS files from your ROM storage."""
import argparse
import os
import shutil
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from . import __version__, budget, cardedit, clean, commands, downloads, edit, external, frontend, inventory, m3u, mirroring, picker, runtime, s3, scrape_plan, store
from . import surprise, themeart, ui, usersettings, vita
from . import collections as colls


SUBCOMMANDS = {  # name -> (usage, one-line summary)
    "sync": ("[CARD]", "download the ROMs, BIOS and scraped data for a card (this is what plain `sync-roms CARD` does)"),
    "edit": ("", "interactive editor: cards, sets, collections, device systems (same as `games edit`)"),
    "games": ("edit|list|add|remove|full|sets|export|import", "edit a card's games, interactively or from scripts"),
    "sets": ("edit", "edit the repo's game sets by hand and open a PR with the changes"),
    "collections": ("edit", "edit your collections of favourite games (saved in ~/.sync-roms/collections/)"),
    "themes": ("update", "copy the latest Art Book Next for ES-DE from GitHub into storage"),
    "cards": ("edit|list|new|set|rename|delete", "list and manage the cards you've synced"),
    "devices": ("[ID]", "list the supported devices, or one device's systems"),
    "upload": ("roms [DIR] | scrapes [CARD]", "upload ROMs or a card's scraped data to storage"),
    "diff": ("[DIR]", "list the ROMs in only DIR or only the bucket, ignoring renames"),
    "scrape": ("[match SYSTEM ROM GAME | review [SYSTEM] | missing [SYSTEM]]", "scrape the ROMs that have no metadata from ScreenScraper into storage's scrapes/ folder"),
    "clean": ("scrapes", "remove scrapes/ media and metadata for ROMs that aren't in storage"),
    "playlist": ("[DIR]", "create or fix the .m3u playlist of every multi-disc game"),
    "convert": ("[DIR]", "unzip archives and convert disc images to verified .chd"),
    "tools": ("install", "brew install the 7z, unar and chdman that `convert` needs"),
    "mirror": ("[DIR] | use DIR | clear", "make or refresh a local copy of everything your lists reference"),
    "cache": ("[update [--full]]", "show the storage cache every command reads file lists and sizes from, or update it"),
    "config": ("show|path", "show the effective settings and where each comes from"),
    "doctor": ("", "check the AWS profile, storage access, tools and your data files"),
    "check": ("", "validate cards.json, surprises.json, the device overlay, the sets and your collections"),
    "completion": ("bash|zsh|fish", "print a shell completion script"),
}

TOPICS = {
    "sync": """
  sync-roms [sync] [CARD] [--dry-run] [--ask] [--yes] [--device ID|full] [--layout NAME] [--no-clean] [--no-eject]

  CARD is the card or folder root (default: the current directory); the chosen firmware decides the folders inside
  it (ES-DE ROMs/ BIOS/, Knulli roms/ bios/, Onion Roms/ BIOS/). Missing folders are created after you confirm.

  FLOW
   1. Pick a device (its recommended systems come from device-systems.json plus your overlay) or Full, then its
      firmware. Remembered per card folder name and used without asking next time; --ask confirms it first.
      --device/--layout set it without the picker (and save it).
   2. Every system with games picked on the card is synced. Interactively, the card editor opens after the
      Surprise step, showing the card's size and how much isn't on it yet as you add games and collections.
   3. Local ROMs no longer in a system's list, in a system with no games listed, or in a system the card's device no longer lists, are listed and, after you confirm (default no), deleted first so the free space shown is accurate.
      Then totals and free space are shown and you confirm; ROMs download, then BIOS.
   4. Scraped data for the card's games is installed from storage's scrapes/ folder, then media on the
      card for ROMs it doesn't have is removed.
   5. BIOS for every system with ROMs on the card is installed, games picked or not. Other systems' ROM folders are never touched.

  --dry-run   show what would be downloaded and deleted, change nothing
  --yes       answer every prompt with its default (a default-no prompt, like deleting files, stays no)
  --no-clean  skip the end-of-run card tidy (.metadata_never_index, .fseventsd, dot_clean)
  --no-eject  leave the card mounted (by default a Mac unmounts all of its volumes after a run with no failures;
              "eject": false in settings.json turns that off for every run)

  A finished run (not --dry-run) creates .metadata_never_index in CARD, empties its .fseventsd, and on a Mac runs
  dot_clean (falling back to sudo mdutil, which asks for your password). ES-DE: files in the Android media folders
  are removed and a .nomedia added after asking once per card name (the answer is remembered; --ask confirms it).
""",
    "games": """
  sync-roms games edit                        interactive editor (cards, sets, device systems)
  sync-roms games list --card NAME [--json]
  sync-roms games add SYSTEM KEY... --card NAME [-n]      KEY: file name, SYSTEM/file key, or a glob like 'Mario*'
  sync-roms games remove SYSTEM KEY... --card NAME [-n]
  sync-roms games full SYSTEM on|off --card NAME [-n]
  sync-roms games sets list | add ID | remove ID --card NAME [-n]
  sync-roms games export --card NAME        one SYSTEM/file per line (full systems as 'SYSTEM/*'), then '@collections ID', '@frontend_collections NAME', '@surprise false' (only when Surprise is off) and '@surprises SYSTEM/file' lines
  sync-roms games import FILE --card NAME [-n]            add the games in such a file; '@' lines replace the card's collections / frontend_collections / surprises, and set Surprise on or off

  --card NAME is required: a card's games are saved in ~/.sync-roms/cards.json with the previous version kept as .bak. Removing only drops a game from the list.
  In the editor: / filters, Space toggles a row, a all/none shown, u reverts the list, o cycles all/on/changed, f toggles a whole set or system.
""",
    "sets": """
  sync-roms sets edit                         edit the repo's sets (games, categories, new and deleted sets), then open a PR

  Needs git and the GitHub CLI (gh, logged in). Your edits are written to a temporary clone of kelsin/sync-roms, pushed
  as a branch and opened as a PR; nothing is written to storage or to ~/.sync-roms.
  Pick a set to switch games off, add games from a system (you're asked for a category), change a game's category or
  rename it. ➕ New set creates one; d deletes the highlighted one. Esc reviews the changes before the PR is opened.
""",
    "collections": """
  sync-roms collections edit                  edit your collections of favourite games

  Your own lists of games (like a set, but personal), saved straight to ~/.sync-roms/collections/<id>.json when you pick
  Done; Quit discards. No git or gh needed, and nothing goes to storage or the repo. Same keys as the set editor.
  Deleting a collection that cards use asks first, then removes it from them. In a card's system list, l adds a
  collection to that card. Theme art picks the picture (Action, RPG, ...) the collection gets on ES-DE and Knulli cards
  that use Art Book Next.
""",
    "themes": """
  sync-roms themes update [--dry-run]         put the latest Art Book Next for ES-DE in storage

  Downloads the GitHub archive of the theme's latest commit (about 200 MB) and replaces os/esde/themes/ in storage
  (write profile). Syncs copy it from there onto ES-DE cards that use Art Book Next, so the Surprise collection has its
  art; a card's copy is replaced when storage has a newer commit. Does nothing when storage already has the latest.
""",
    "edit": """
  sync-roms edit                              main menu: Cards, Sets (opens a PR), Collections, Device systems; same as `games edit`
""",
    "cards": """
  sync-roms cards edit                        same as `games edit`
  sync-roms cards list [--json]
  sync-roms cards new NAME --device ID|full --layout NAME [--size 512GB]
  sync-roms cards set NAME [--device ID|full] [--layout NAME] [--size 512GB]
  sync-roms cards rename OLD NEW
  sync-roms cards delete NAME [--yes]

  A card is a folder name (the card root's basename) with a remembered device, firmware and games.
""",
    "devices": """
  sync-roms devices [ID] [--json]

  Without an ID: every device with its chip and system count. With one: its firmwares, note and systems.
""",
    "upload": """
  sync-roms upload roms [DIR] [--replace] [--dry-run]    upload the ROMs in DIR (default: current directory) to storage folder of a system you pick
  sync-roms upload scrapes [CARD] [--dry-run]            upload CARD/ES-DE scraped data to storage's scrapes/ folder, merging with what's there

  The system is guessed from the folder name; same-size files are skipped, a different size overwrites after you confirm.
  --replace makes the storage folder match DIR: renamed files are moved by content, and left-over storage files are listed
  so you pick which to delete. Uploads use the write profile (ROMS_WRITE_PROFILE, default 'roms').
""",
    "diff": """
  sync-roms diff [DIR]

  Lists the ROMs in only one of DIR and storage folder of a system you pick. Same path and size is the same file;
  the rest are matched by content (the CRCs inside zips).
""",
    "scrape": """
  sync-roms scrape [--system ID] [--all] [--retry] [--fill-media] [--skip-media TYPES] [--dry-run]
  sync-roms scrape match SYSTEM ROM GAME_ID_OR_NAME [--skip-media TYPES] [--dry-run]
  sync-roms scrape review [SYSTEM]
  sync-roms scrape missing [SYSTEM] [--all]
  sync-roms scrape --set-credentials

  Looks up every available ROM with no entry in scrapes/<system>/metadata.json on ScreenScraper and writes its
  metadata and media (and the Onion/Slot images) to storage. The ROMs and how each will be
  looked up are listed first. ROMs ScreenScraper doesn't know are remembered and skipped until --retry.
  --system ID        only that storage folder (e.g. gba)
  --all              every ROM in the storage, not just those your cards list (games, sets, full systems)
  --fill-media       also scrape ROMs that have metadata but lack some media type in storage (ScreenScraper is asked
                     again for each, even when it has no such media); their existing metadata is kept
  --skip-media TYPES comma-separated media folders not to download (covers, 3dboxes, backcovers, fanart, manuals,
                     marquees, ...); other values are refused with the list
  --dry-run          list the ROMs and the metadata and media folders that would be written; no ScreenScraper
                     credentials or requests (scrape match --dry-run does look the game up)
  match              say which ScreenScraper game a ROM is (a game id, or a name to search and pick from), then scrape it;
                     for a ROM that already has metadata it asks before replacing the entry and deleting its old media
  review             go through the ROMs ScreenScraper calls non-games or doesn't know: ignore, search under another
                     name and scrape the game picked, or keep for later
  missing            list every ROM with no metadata and why (non-game, not on ScreenScraper, matched but not scraped,
                     not looked up yet); nothing is looked up. --all: every ROM in the storage
  --set-credentials  ask for your ScreenScraper username and password (saved in settings.json,
                     readable only by you; blank keeps the current value)
  When ScreenScraper's daily quota runs out the run stops cleanly; run it again tomorrow. Writes use the write profile.
""",
    "clean": """
  sync-roms clean scrapes [--dry-run]

  Removes scrapes/ media and metadata for ROMs that aren't in storage at all (asks first).
""",
    "playlist": """
  sync-roms playlist [DIR] [--dry-run]

  Creates or fixes the .m3u of every multi-disc game ("Name (Disc 1).chd", "Name (Disc 2).chd") in DIR and its
  subfolders. Playlists whose files are all missing are deleted (asks first). Local only. (Old name: --m3u)
""",
    "convert": """
  sync-roms convert [DIR] [--dry-run]

  Unzips (7z, or unar for .rar) every .zip/.7z/.rar, and the archives inside them, and converts each disc image (.cue, .gdi, .toc, .iso) to a verified .chd (Xbox .iso to xiso, Xbox 360 .iso to .zar),
  per the `chd` key in systems.json of the system whose folder it is in. Archives and images are removed once their chd verifies,
  then the .m3u playlists are fixed. Needs 7z, chdman and, for Xbox, extract-xiso and, for Xbox 360, iso2zar (see `tools install`). (Old names: --cd, --chd)
""",
    "tools": """
  sync-roms tools install

  brew install the 7z (sevenzip), unar and chdman (rom-tools) that `convert` needs, and say how to build extract-xiso and iso2zar.
""",
    "mirror": """
  sync-roms mirror [DIR] [--dry-run]     make or refresh a local copy of everything the lists reference (no DIR: the saved mirror)
  sync-roms mirror use DIR               refresh DIR, then save it so every sync refreshes it first and copies from it
  sync-roms mirror clear                 forget the saved mirror (its files stay)

  Files no longer referenced are deleted (after confirming when it is a lot).
""",
    "config": """
  sync-roms config show      the effective bucket, endpoint, profiles and mirror, and where each came from
  sync-roms config path      the data folder
""",
    "cache": """
  sync-roms cache [update [--full]]

  Every command reads what storage holds (file names, sizes and, for a bucket, ETags) from a cache in
  ~/.sync-roms/storage-cache.json; only the files themselves are downloaded from storage. Nothing refreshes it on its
  own: sync-roms's own uploads, moves and deletes keep it up to date, and after changing storage any other way run
  `sync-roms cache update`.

  cache          where the cache was read from, when it was last updated, and its files and size per folder
  cache update   read storage again: one listing of a bucket, or a walk of a folder that stats only files the
                 cache doesn't have; the rest keep their cached size
  --full         in a folder, stat every file too (catches files replaced under the same name; a bucket listing is
                 the same either way)

  With no cache for the storage in use, the first command that reads storage offers to build it. Saying no is
  remembered (storage_cache_declined in settings.json), and commands then list storage each run.
""",
    "doctor": """
  sync-roms doctor

  Checks the AWS profile and storage access, the tools `convert` needs, and that your data files parse.
""",
    "check": """
  sync-roms check [--bucket-keys]

  Validates cards.json, surprises.json, device-systems.json and the sets: bad JSON,
  unknown systems, devices and sets. Exits 1 if anything is wrong.
  --bucket-keys also lists storage (read-only profile) and reports every game or set file it doesn't have.
""",
    "completion": """
  sync-roms completion bash|zsh|fish

  Prints a completion script, e.g.  sync-roms completion zsh > ~/.zfunc/_sync-roms
""",
}


def help_text(topic=None):
    if topic in TOPICS:
        return f"\n{ui.bold('🎮 sync-roms ' + topic)} — {SUBCOMMANDS[topic][1]}\n{TOPICS[topic]}"
    rows = "\n".join(f"  {ui.green(name):<{20 + len(ui.green(''))}} {ui.cyan(usage) if usage else ''}\n      {summary}"
                     for name, (usage, summary) in SUBCOMMANDS.items())
    return f"""
{ui.bold('🎮 sync-roms')} — download ROMs and BIOS files from your ROM storage (an S3 bucket or a folder)

{ui.bold('USAGE')}
  {ui.green('sync-roms')} [{ui.cyan('CARD')}]                 sync a card (same as `sync-roms sync CARD`)
  {ui.green('sync-roms')} {ui.cyan('COMMAND')} [options]      one of the commands below; `sync-roms COMMAND --help` explains it

{ui.bold('COMMANDS')}
{rows}

{ui.bold('GLOBAL OPTIONS')}
  {ui.yellow('-n, --dry-run')}   show what would happen, change nothing (commands that can't honor it refuse it)
  {ui.yellow('-y, --yes')}       answer prompts with their default (deleting stays "no")
  {ui.yellow('--quiet')}         print only errors, warnings and --json data (prompts go to stderr)      {ui.yellow('--verbose')}   also print the effective settings
  {ui.yellow('--json')}          machine-readable output for devices, diff and `sync --dry-run` (use --device/--layout to skip the pickers)
  {ui.yellow('--profile P')} {ui.yellow('--write-profile P')} {ui.yellow('--bucket B')} {ui.yellow('--root DIR')} {ui.yellow('--endpoint URL')}   override those settings for this run
  {ui.yellow('-a, --ask')}       sync: confirm the saved device/firmware and Android media choice instead of using it silently
  {ui.yellow('--version')}       print the version      {ui.yellow('-h, --help')}   this screen

{ui.bold('ENVIRONMENT')}
  {ui.yellow('ROMS_BUCKET')}  {ui.yellow('ROMS_ROOT')}  {ui.yellow('ROMS_ENDPOINT')}  {ui.yellow('ROMS_PROFILE')} (default roms-readonly)  {ui.yellow('ROMS_WRITE_PROFILE')} (default roms)
  override settings.json "bucket", "root" (a folder, e.g. a mounted network share, used instead of storage), "endpoint", "profile", "write_profile"; the flags above override these. {ui.yellow('NO_COLOR')} / {ui.yellow('FORCE_COLOR')} control colors.

{ui.bold('EXIT CODES')}
  0 done (or nothing to do, or you declined)   1 some files failed   2 bad usage   3 setup problem (credentials, bucket, tools, bad data file)   130 interrupted

{ui.bold('EXAMPLES')}
  sync-roms /Volumes/SD                          sync the card
  sync-roms sync /Volumes/SD --device rg35xx-sp --layout knulli --yes --dry-run
  sync-roms games add gba 'Metroid*' --card SD   add games to a card
  sync-roms upload roms ~/roms/gba               upload ROMs to storage

  {ui.dim('The old flags (--edit, --upload, --upload-scrapes, --clean-scrapes, --m3u, --cd, --install-tools, --mirror,')}
  {ui.dim('--use-mirror, --clear-mirror, --devices) still work. A card folder named like a command: write ./edit.')}
"""


def check_dir(path, label):
    """Fail early if `path` can't be used or created. Returns True if it must be created."""
    if os.path.exists(path):
        if not os.path.isdir(path):
            ui.fail(f"{label} {path} exists but is not a directory", 3)
        if not os.access(path, os.W_OK | os.X_OK):
            ui.fail(f"No write permission for {label} {path}", 3)
        return False
    parent = os.path.dirname(path)
    while not os.path.exists(parent):
        parent = os.path.dirname(parent)
    if not os.path.isdir(parent) or not os.access(parent, os.W_OK | os.X_OK):
        ui.fail(f"Can't create {label} {path}: no write permission in {parent}", 3)
    return True


def prepare_dirs(base, layout, dry_run, ask=True):
    """Show, validate and (after confirmation, unless ask is False) create the layout's ROM and BIOS folders under base.

    Returns (roms, bios), or None if declined.
    """
    roms = os.path.join(base, layout["roms_dir"])
    bios = os.path.join(base, layout["bios_dir"])
    # check everything before asking anything
    missing = {path for label, path in (("ROMs folder", roms), ("BIOS folder", bios)) if check_dir(path, label)}
    print(ui.bold(f"📁 {layout['label']} layout in {base}:"))
    for icon, name, path in (("💿", "ROMs", roms), ("🧠", "BIOS", bios)):
        print(f"  {icon} {name} → {ui.cyan(path)}" + (ui.dim("  (will be created)") if path in missing else ""))
    if ask and not dry_run and not ui.confirm("Continue with these folders?"):
        return None
    for path in sorted(missing):
        if dry_run:
            print(ui.yellow(f"🧪 Would create {path}"))
        else:
            os.makedirs(path)
    return roms, bios


def main():
    if not sys.stdout.isatty():  # logs and pipes get plain text
        sys.stdout = ui.PlainOut(sys.stdout)
    try:
        return sync()
    except KeyboardInterrupt:
        print(ui.yellow("\n🛑 Interrupted"), file=sys.stderr)
        return 130
    except NoCredentialsError:
        ui.fail(f"No AWS credentials for profile '{runtime.PROFILE}'. Run: aws configure --profile {runtime.PROFILE}", 3)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        hint = {
            "ExpiredToken": f"the session expired: aws sso login --profile {runtime.PROFILE}",
            "InvalidAccessKeyId": f"the access key is wrong: aws configure --profile {runtime.PROFILE}",
            "SignatureDoesNotMatch": f"the secret key is wrong: aws configure --profile {runtime.PROFILE}",
            "NoSuchBucket": f"bucket '{runtime.BUCKET}' doesn't exist: check ROMS_BUCKET or settings.json",
            "AccessDenied": f"profile '{runtime.PROFILE}' can't read bucket '{runtime.BUCKET}'",
            "403": f"profile '{runtime.PROFILE}' can't read bucket '{runtime.BUCKET}'",
        }.get(code, "")
        ui.fail(f"S3 said {code or 'an error'}: {e.response.get('Error', {}).get('Message', e)}" + (f"\n   → {hint}" if hint else ""), 3)
    except BotoCoreError as e:
        ui.fail(f"Couldn't reach S3: {e}\n   → check your network, ROMS_ENDPOINT, and `aws sts get-caller-identity --profile {runtime.PROFILE}`", 3)
    except OSError as e:  # e.g. the storage share dropped mid-run
        ui.fail(str(e), 1)
    finally:
        inventory.flush()
        clean.clean_dirs()
        clean.eject()


def list_devices(args=None):
    """Print a table of the devices (name, chip, number of recommended systems), or one device's details given its id."""
    catalog = store.load_catalog()
    return commands.show_devices(catalog["devices"], catalog["systems"], getattr(args, "device_id", None), getattr(args, "json", False))


class Parser(argparse.ArgumentParser):
    literal = frozenset()  # the values after --scrape-match that start with a dash: values, never options

    def error(self, message):
        ui.fail(f"{message}\n   Try 'sync-roms --help'.", 2)

    def parse_known_args(self, args=None, namespace=None):
        args = list(sys.argv[1:] if args is None else args)
        if "--scrape-match" in args:
            i = args.index("--scrape-match")
            self.literal = frozenset(a for a in args[i + 1:i + 4] if a.startswith("-"))
        return super().parse_known_args(args, namespace)

    def _parse_optional(self, arg_string):
        return None if arg_string in self.literal else super()._parse_optional(arg_string)


# subcommand -> the legacy flags it stands for. {rest} are its remaining arguments.
LEGACY = {
    ("sync",): [], ("devices",): ["--devices"], ("diff",): ["--diff"], ("playlist",): ["--m3u"], ("convert",): ["--cd"],
    ("tools", "install"): ["--install-tools"], ("clean", "scrapes"): ["--clean-scrapes"],
    ("scrape", "match"): ["--scrape-match"], ("scrape", "review"): ["--scrape-review"],
    ("scrape", "missing"): ["--scrape-missing"], ("scrape",): ["--scrape"],
    ("upload", "roms"): ["--upload"], ("upload", "scrapes"): ["--upload-scrapes"],
    ("mirror", "use"): ["--use-mirror"], ("mirror", "clear"): ["--clear-mirror"], ("mirror",): ["--mirror"],
    ("games", "edit"): ["--edit"], ("cards", "edit"): ["--edit"], ("edit",): ["--edit"],
}
BOOL_FLAGS = {"-n", "--dry-run", "-y", "--yes", "-a", "--ask"}
PLAIN_FLAGS = BOOL_FLAGS | {"--replace", "--json", "--no-clean", "--no-eject", "--retry", "--all", "--fill-media", "--set-credentials"}
VALUE_FLAGS = {"--system", "--device", "--layout", "--device-id", "--skip-media"}


def translate(argv):
    """Rewrite `sync-roms COMMAND ...` into the flag form the rest of the code reads. Global flags may come first."""
    i = 0
    while i < len(argv) and argv[i] in BOOL_FLAGS | {"--json"}:
        i += 1
    if i >= len(argv) or argv[i] not in SUBCOMMANDS:
        return argv
    head, rest = argv[:i], argv[i + 1:]
    name = argv[i]
    for words in sorted(LEGACY, key=len, reverse=True):
        if words[0] == name and tuple(rest[:len(words) - 1]) == words[1:]:
            tail = rest[len(words) - 1:]
            flags = LEGACY[words]
            if not flags:
                return head + tail
            if words == ("scrape", "match"):  # three values that must stay together, behind the flag
                n = 0  # flags may come first; from the first value on, the next three words are the values
                while n < len(tail) and tail[n].startswith("-"):
                    n += 2 if tail[n] in VALUE_FLAGS else 1
                return head + flags + tail[n:n + 3] + tail[:n] + tail[n + 3:]
            n = 0  # flags (and the values of value flags) before the mode's value (`diff -n /x`) move behind it
            while n < len(tail) and (tail[n] in PLAIN_FLAGS or tail[n] in VALUE_FLAGS):
                n += 1 if tail[n] in PLAIN_FLAGS else 2
            if n < len(tail) and not tail[n].startswith("-"):
                value = ["--device-id", tail[n]] if name == "devices" else [tail[n]]
                return head + flags + value + tail[:n] + tail[n + 1:]
            return head + flags + tail
    if name == "upload" or name == "clean" or name == "tools":
        ui.fail(f"'{name}' needs a subcommand: " + ", ".join(
            f"{w[0]} {w[1]}" for w in LEGACY if w[0] == name and len(w) > 1), 2)
    return argv


def build_parser():
    ap = Parser(add_help=False, allow_abbrev=False)
    ap.add_argument("base_dir", nargs="?")
    ap.add_argument("-n", "--dry-run", action="store_true")
    ap.add_argument("-y", "--yes", action="store_true")
    ap.add_argument("-e", "--edit", action="store_true")
    ap.add_argument("-a", "--ask", action="store_true")
    ap.add_argument("-u", "--upload-scrapes", action="store_true")
    ap.add_argument("-c", "--clean-scrapes", action="store_true")
    ap.add_argument("--upload", nargs="?", const="")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--scrape", action="store_true")
    ap.add_argument("--scrape-match", nargs=3, metavar=("SYSTEM", "ROM", "GAME"))
    ap.add_argument("--scrape-review", nargs="?", const="", metavar="SYSTEM")
    ap.add_argument("--scrape-missing", nargs="?", const="", metavar="SYSTEM")
    ap.add_argument("--retry", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--fill-media", action="store_true")
    ap.add_argument("--skip-media")
    ap.add_argument("--set-credentials", action="store_true")
    ap.add_argument("--diff", nargs="?", const="")
    ap.add_argument("--m3u", nargs="?", const="")
    ap.add_argument("--cd", "--chd", dest="chd", nargs="?", const="")
    ap.add_argument("--install-tools", action="store_true")
    ap.add_argument("--mirror", nargs="?", const="")
    ap.add_argument("--use-mirror")
    ap.add_argument("--clear-mirror", action="store_true")
    ap.add_argument("--devices", action="store_true")
    ap.add_argument("--device-id")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--system")
    ap.add_argument("--device")
    ap.add_argument("--layout")
    ap.add_argument("--no-clean", action="store_true")
    ap.add_argument("--no-eject", action="store_true")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    return ap


def check_modes(args):
    """Refuse flag combinations that would silently do nothing. Returns the active mode's name (None for a plain sync)."""
    modes = [name for name, on in (
        ("--edit", args.edit), ("--upload", args.upload is not None), ("--diff", args.diff is not None),
        ("--upload-scrapes", args.upload_scrapes), ("--clean-scrapes", args.clean_scrapes),
        ("--scrape", args.scrape), ("--scrape-match", args.scrape_match is not None),
        ("--scrape-review", args.scrape_review is not None), ("--scrape-missing", args.scrape_missing is not None),
        ("--mirror", args.mirror is not None), ("--use-mirror", bool(args.use_mirror)), ("--clear-mirror", args.clear_mirror),
        ("--m3u", args.m3u is not None), ("--cd", args.chd is not None), ("--install-tools", args.install_tools),
        ("--devices", args.devices)) if on]
    if len(modes) > 1:
        ui.fail(f"{' and '.join(modes[:2])} can't be combined: use one command at a time", 2)
    mode = modes[0] if modes else None
    if args.replace and mode != "--upload":
        ui.fail("--replace only works with `upload roms` (--upload)", 2)
    if args.dry_run and mode in ("--edit", "--install-tools", "--clear-mirror", "--devices", "--scrape-missing"):
        ui.fail(f"--dry-run has no effect on {mode}", 2)
    if args.ask and mode:
        ui.fail(f"--ask only applies to syncing a card, not {mode}", 2)
    if (args.device or args.layout or args.no_clean or args.no_eject) and mode:
        ui.fail(f"--device, --layout, --no-clean and --no-eject only apply to syncing a card, not {mode}", 2)
    if args.base_dir and mode not in (None, "--upload-scrapes", "--clean-scrapes"):
        ui.fail(f"{mode} doesn't take a card folder ({args.base_dir!r}); give the directory right after the command", 2)
    if args.device_id and mode != "--devices":
        ui.fail("a device id only applies to `devices`", 2)
    if args.json and not (mode in ("--devices", "--diff") or (mode is None and args.dry_run)):
        ui.fail("--json only applies to `devices`, `diff` and `sync --dry-run`", 2)
    if args.system and mode not in ("--diff", "--scrape"):
        ui.fail("--system only applies to `diff` and `scrape`", 2)
    if args.retry and mode != "--scrape":
        ui.fail("--retry only applies to `scrape`", 2)
    if args.all and mode not in ("--scrape", "--scrape-missing"):
        ui.fail("--all only applies to `scrape` and `scrape missing`", 2)
    if args.fill_media and mode != "--scrape":
        ui.fail("--fill-media only applies to `scrape`", 2)
    if args.set_credentials and (mode != "--scrape" or args.system or args.retry or args.all or args.fill_media or args.skip_media or args.dry_run):
        ui.fail("--set-credentials only goes with `scrape`, on its own", 2)
    if args.skip_media is not None:
        if mode not in ("--scrape", "--scrape-match"):
            ui.fail("--skip-media only applies to `scrape`", 2)
        args.skip_media = [t.strip() for t in args.skip_media.split(",") if t.strip()]
        from . import scrape_online
        scrape_online._check_skip(args.skip_media)
    return mode


GLOBAL_VALUE_FLAGS = {"--profile": "profile", "--write-profile": "write_profile", "--bucket": "bucket", "--root": "root", "--endpoint": "endpoint"}
DATA_COMMANDS = {("devices",), ("completion",), ("games", "list"), ("games", "export"), ("cards", "list"), ("config", "path")}


def extract_globals(argv):
    """Remove --profile/--write-profile/--bucket/--root/--endpoint (set in runtime.OVERRIDES) and --quiet/--verbose from argv.
    Returns (the rest of argv, quiet, verbose)."""
    runtime.OVERRIDES.clear()
    rest, flags, i = [], set(), 0
    while i < len(argv):
        arg = argv[i]
        name, eq, value = arg.partition("=")
        if name in GLOBAL_VALUE_FLAGS:
            if not eq:
                if i + 1 >= len(argv):
                    ui.fail(f"{name} needs a value", 2)
                i += 1
                value = argv[i]
            runtime.OVERRIDES[GLOBAL_VALUE_FLAGS[name]] = value
        elif arg in ("--quiet", "--verbose"):
            flags.add(arg)
        else:
            rest.append(arg)
        i += 1
    if len(flags) == 2:
        ui.fail("--quiet and --verbose can't be combined", 2)
    return rest, "--quiet" in flags, "--verbose" in flags


def is_data_command(argv):
    """Whether the command's stdout is its result (so --quiet must not discard it)."""
    words = tuple(a for a in argv if not a.startswith("-"))
    return "--devices" in argv or any(words[:len(d)] == d for d in DATA_COMMANDS)


def sync():
    argv, quiet, verbose = extract_globals(sys.argv[1:])
    ui.set_output(quiet and not is_data_command(argv), verbose)
    try:
        usersettings.apply_settings()
        if ui.VERBOSE:
            for name, (value, source) in usersettings.resolve_settings().items():
                ui.debug(f"{name} = {value} ({source})")
        return run(argv)
    finally:
        ui.reset()


def run(argv):
    if "-u" in argv:
        ui.warn("-u is deprecated: it means --upload-scrapes, not --upload. Use `sync-roms upload scrapes` instead.")
    lead = 0
    while lead < len(argv) and argv[lead] in BOOL_FLAGS:
        lead += 1
    if lead < len(argv) and argv[lead] in commands.COMMANDS and argv[lead:lead + 2] not in (["games", "edit"], ["cards", "edit"]):
        cmd = argv[lead:] + argv[:lead]  # leading global flags go after the command, where its parser reads them
        if "-h" in cmd or "--help" in cmd:
            print(help_text(cmd[0]))
            return 0
        return commands.run(cmd)
    if argv and argv[0] == "help":
        print(help_text(argv[1] if len(argv) > 1 else None))
        return 0
    topic = next((a for a in argv if a in SUBCOMMANDS), None) if ("-h" in argv or "--help" in argv) else None
    argv = translate(argv)
    args = build_parser().parse_args(argv)
    if args.version:
        print(f"sync-roms {__version__}")
        return 0
    if args.help:
        print(help_text(topic))
        return 0
    ui.ASSUME_YES = args.yes
    mode = check_modes(args)
    if args.json and mode in (None, "--diff"):  # the JSON document is all that reaches stdout
        ui.set_output(True, ui.VERBOSE)
    handled, code = dispatch_mode(args, mode)
    return code if handled else sync_card(args)


def dispatch_mode(args, mode):
    """Run the command a flag stands for. Returns (True, its exit code), or (False, None) for a plain sync.

    The modules a command needs are imported here, so the other commands (and --help) don't pay for them."""
    if args.devices:
        return True, list_devices(args)
    if mode in ("--m3u", "--cd", "--install-tools"):
        if args.install_tools:
            return True, external.install_tools_command()
        if args.chd is not None:
            from . import chd
            return True, chd.chd_command(args)
        return True, m3u.m3u_command(args)
    if args.set_credentials:
        from . import scrape_online
        return True, scrape_online.set_credentials()
    usersettings.ensure_bucket()
    if runtime.ROOT and not os.path.isdir(runtime.ROOT) and not args.edit:  # the editor goes by the cache alone
        ui.fail(f"The storage folder {runtime.ROOT} isn't there (is the share mounted?)", 3)
    if not args.json:  # the JSON document is all that reaches stdout: no question
        inventory.prepare()
    if args.scrape:
        from . import scrape_online
        return True, scrape_online.scrape_command(args)
    if args.scrape_match:
        from . import scrape_online
        args.system, args.rom, args.game = args.scrape_match
        return True, scrape_online.match_command(args)
    if args.scrape_review is not None:
        from . import scrape_review
        args.system = args.scrape_review or None
        return True, scrape_review.review_command(args)
    if args.scrape_missing is not None:
        from . import scrape_online
        args.system = args.scrape_missing or None
        return True, scrape_online.missing_command(args)
    if args.upload is not None:
        from . import upload
        return True, upload.upload_command(args)
    if args.diff is not None:
        from . import diff
        return True, diff.diff_command(args)
    if args.mirror is not None or args.use_mirror or args.clear_mirror:
        from . import mirroring
        return True, mirroring.mirror_command(args)
    if args.edit or args.upload_scrapes or args.clean_scrapes:
        if args.edit:
            code = edit.edit_manifest()
        else:
            from . import scrape_files
            code = scrape_files.upload_scrapes(args) if args.upload_scrapes else scrape_files.clean_scrapes(args)
        mirror = usersettings.load_settings().get("mirror")
        if mirror and not code and not args.dry_run:  # pick up the games just added
            from . import mirroring
            print()
            mirroring.use_mirror(mirror, False)
        return True, code
    return False, None


def choose_card_setup(args, base, card, manifest, saved):
    """(device or None for Full, layout name, (roms dir, bios dir)) from --device/--layout, the saved setup or the picker.
    None if the user cancelled."""
    devices, layouts = manifest["devices"], manifest["layouts"]
    dirs = None
    setup = picker.saved_setup(saved, devices, layouts, card)
    if args.device or args.layout:
        setup = commands.setup_from_flags(manifest, setup, args.device, args.layout)
        print(ui.bold(f"🎛️  {ui.cyan(card)}: ") + f"{setup[0]['name'] if setup[0] else 'Full'} · {layouts[setup[1]]['label']}")
        device, layout_name = setup
        dirs = prepare_dirs(base, layouts[layout_name], args.dry_run, ask=False)
        if dirs and not args.dry_run:
            store.save_card(card, device, layout_name)
    elif setup:
        device, layout_name = setup
        print(ui.bold(f"💾 Remembered {ui.cyan(card)}: ")
              + f"{device['name'] if device else 'Full'} · {layouts[layout_name]['label']}"
              + ui.dim("  (saved under this folder name; --ask or --device/--layout changes it)"))
        if not args.ask or ui.confirm("Use this saved setup?"):
            dirs = prepare_dirs(base, layouts[layout_name], args.dry_run, ask=False)
    if dirs is None:
        device, layout_name = picker.choose_setup(manifest)
        dirs = prepare_dirs(base, layouts[layout_name], args.dry_run)
        if dirs is None:
            print(ui.yellow("👋 Cancelled."))
            return None
        if not args.dry_run:
            store.save_card(card, device, layout_name)
    return device, layout_name, dirs


def total_bytes(jobs):
    return sum(j[2] or 0 for j in jobs)


def delete_extras(extras):
    """List the local ROMs that are no longer wanted and, after confirming, delete them."""
    print(ui.bold(f"\n🗑️  {len(extras)} local ROM(s) are no longer in the selection"))
    for path in extras[:10]:
        print(ui.dim(f"     {path}"))
    if len(extras) > 10:
        print(ui.dim(f"     … and {len(extras) - 10} more"))
    answer = ui.choose(f"Delete these {len(extras)} local file(s) ({ui.human_size(sum(os.path.getsize(p) for p in extras))})?", "ynl", "n", "y yes · n no · l list all")
    while answer == "l":
        for path in extras:
            print(ui.dim(f"     {path}"))
        answer = ui.choose(f"Delete these {len(extras)} local file(s)?", "yn", "n")
    if answer == "y":
        deleted = 0
        for path in dict.fromkeys(extras):
            try:
                os.remove(path)
                deleted += 1
            except FileNotFoundError:  # already gone (a duplicate entry, or removed meanwhile)
                pass
            except OSError as e:
                print(ui.red(f"  ❌ {path}: {e}"))
        print(ui.green(f"  🧹 Deleted {deleted} file(s)"))
    else:
        print(ui.yellow("  ↩️  Keeping them"))


def remove_stale_media(stale):
    """Delete the media files left for ROMs that aren't on the card, saying so."""
    if stale:
        print(ui.bold(f"\n🧹 Removing {len(stale)} media file(s) for ROMs that aren't on this card"))
        for path in stale[:5]:
            print(ui.dim(f"     {path}"))
        if len(stale) > 5:
            print(ui.dim(f"     … and {len(stale) - 5} more"))
    for path in stale:
        try:
            os.remove(path)
        except OSError as e:
            print(ui.red(f"  ❌ {path}: {e}"))
    if stale:
        print(ui.green(f"🧹 Removed {len(stale)} media file(s) for ROMs that aren't on this card"))


def report_failures(failures):
    print(ui.red(f"\n❌ {len(failures)} file(s) failed:"))
    for key, reason in failures[:20]:
        print(f"   {key}: {ui.dim(reason)}")
    if len(failures) > 20:
        print(ui.dim(f"   … and {len(failures) - 20} more"))
    print(ui.dim("   Files already downloaded are skipped, so run the same command again to retry just these."))


def sync_card(args):
    from . import chd
    store.preload_repo_data()
    base = os.path.abspath(os.path.expanduser(args.base_dir or os.getcwd()))
    if not os.path.isdir(base):
        ui.fail(f"{base} isn't a folder (is the card mounted?)\n   See sync-roms --help for the commands.", 2)

    tree = inventory.current()
    age = f"  ·  cache updated {inventory._ago(max(0, inventory._clock() - tree.updated))}" if tree and tree.updated else ""
    print(ui.bold("🎮 sync-roms") + ui.dim(f"  {s3.access()}{age}"))
    mirror = usersettings.load_settings().get("mirror")
    if mirror:
        mirroring.use_mirror(mirror, args.dry_run)
    print("📄 Fetching manifests...")
    card = os.path.basename(base) or base
    manifest = store.load_manifest([card])
    systems, layouts = manifest["systems"], manifest["layouts"]
    if not any(s["games"] or s.get("full_system") for s in systems):
        print(ui.dim(f"  {card} has no games picked"))
    old_list = os.path.join(store.data_dir(), "games.json")  # the core list from before cards had their own games
    if os.path.exists(old_list) and store.personal_json("games.json"):
        ui.warn(f"{old_list} is no longer read; pick its games for {card} in 'sync-roms edit'.")
    saved = store.load_cards().get(card)
    chosen_setup = choose_card_setup(args, base, card, manifest, saved)
    if chosen_setup is None:
        return 0
    device, layout_name, dirs = chosen_setup
    layout = layouts[layout_name]
    unzip = layout.get("unzip", False)  # ROMs go in flat and unzipped (Slot)
    disc_dir = layout.get("disc_dir")  # multi-disc games' discs go in this hidden folder, their playlist beside it (Onion)
    onion = layout_name in scrape_plan.ONION_LAYOUTS
    roms_dir, bios_dir = dirs
    clean_card = not args.dry_run and not args.no_clean
    dropped = []  # systems the device no longer lists: whatever they left on the card is unwanted
    if device:
        wanted_ids = set(device["systems"])
        dropped = [s for s in systems if s["bucket"] not in wanted_ids]
        systems = [s for s in systems if s["bucket"] in wanted_ids]
        if device["note"]:
            print(ui.dim(f"  {device['name']}: {device['note']}"))
    unsupported = [s for s in systems if not s["folders"].get(layout_name)]
    if unsupported:
        systems = [s for s in systems if s["folders"].get(layout_name)]
        print(ui.dim(f"  {len(unsupported)} system(s) have no {layout['label']} folder and are skipped"))
    systems.sort(key=lambda s: s["name"].lower())

    def reload_systems():
        """The systems this card syncs, with the card's games as they are saved now."""
        fresh = store.load_manifest([card])["systems"]
        if device:
            fresh = [s for s in fresh if s["bucket"] in wanted_ids]
        return sorted((s for s in fresh if s["folders"].get(layout_name)), key=lambda s: s["name"].lower())

    print("📏 Reading ROM sizes...")
    listings = {}  # {system id: {key: size}}, kept until the system's games change
    avail, discs = {}, {}  # per system id: the keys to sync, their multi-disc keys

    sized = not runtime.ROOT or inventory.current() is not None  # sizes are known up front

    def available(s):
        return avail[s["bucket"]]

    def discs_of(s):
        return discs[s["bucket"]]

    def listing_of(s):
        """{key: size} of a system's bucket folder. From a root folder with no storage cache, names only (a share is slow
        to stat): a full system's files are listed, a game list needs no listing, and sizes are read for what gets synced."""
        if not sized:
            return inventory.files(s["bucket"] + "/", sizes=False) if s.get("full_system") else {}
        return store.list_system(s)

    def relist():
        """List the systems not listed yet and work out every system's keys to sync."""
        todo = [s for s in systems if s["bucket"] not in listings]
        with ThreadPoolExecutor(runtime.WORKERS) as ex:
            listings.update(zip((s["bucket"] for s in todo),
                                ex.map(lambda s: listing_of(s)
                                       if s.get("full_system") or store.listed(s) else {}, todo)))
        for s in systems:
            avail[s["bucket"]] = store.available_keys(s, listings[s["bucket"]])
            discs[s["bucket"]] = m3u.disc_keys(avail[s["bucket"]]) if disc_dir else ()

    fetching = {}  # {system id: {key: whether it isn't on the card yet}}: the card's files don't change while editing

    def to_fetch(s, keys):
        """The keys of a system's ROMs that aren't on the card yet, for the card editor's size preview."""
        bucket = s["bucket"]
        seen = fetching.setdefault(bucket, {})
        todo = [k for k in keys if k not in seen]
        if todo:
            sizes = inventory.cached(f"{bucket}/") or {}
            disc_keys = m3u.disc_keys(keys) if disc_dir else ()
            jobs = []
            for k in todo:
                try:
                    path = s3.safe_join(os.path.join(roms_dir, s["folders"][layout_name]),
                                        downloads.rom_rel(k, unzip, disc_dir, disc_keys))
                except ValueError:
                    seen[k] = False
                    continue
                jobs.append((k, path, sizes.get(k)))
            need = {j[0] for j in downloads.plan_downloads(jobs, unzip, disc_dir)}
            seen.update((k, k in need) for k, _, _ in jobs)
        return {k for k in keys if seen[k]}

    relist()
    interactive = not (ui.ASSUME_YES or args.json) and ui.has_terminal()
    surprise.run_surprise(card, (device, layout_name), [s for s in systems if available(s)], interactive, args.dry_run,
                          to_fetch=to_fetch)
    if not args.dry_run:  # the step (and the card editor it opens) may have changed the card's games
        def picks(s):
            return s.get("full_system"), store.listed(s)
        before = {s["bucket"]: picks(s) for s in systems}
        systems = reload_systems()
        changed = [s["bucket"] for s in systems if picks(s) != before.get(s["bucket"])]
        if changed and runtime._mirror_root:  # the new picks reach the mirror before they are copied from it
            root = runtime._mirror_root
            try:
                with mirroring.storage_reads():
                    failed = mirroring.refresh_mirror(root)
                if failed:
                    ui.warn(f"{failed} mirror download(s) failed; files missing from the mirror will fail to copy. Re-run to retry")
            except (*s3.ERRORS, SystemExit) as e:  # S3 failed, or the folder isn't a mirror
                ui.warn(f"Couldn't refresh the mirror ({e}); using what it has")
        for bucket in changed:
            listings.pop(bucket, None)
        relist()
        saved = store.load_cards().get(card)
    chosen = [s for s in systems if available(s)]
    if not chosen:
        print(ui.yellow(f"👋 {card} has nothing to sync."))
        return 0
    print(ui.bold(f"\n🔎 Checking {len(chosen)} system(s) against storage..."))

    def dest_of(s):
        return os.path.join(roms_dir, s["folders"][layout_name])

    def rom_bios_names(s):
        """The names the system's ROM-folder BIOS files have on the card."""
        return {os.path.basename(f) for f in s["bios"].get("rom_files", [])}

    rom_jobs, missing, extras, moved = [], [], [], set()
    for s in chosen:
        wanted = available(s)
        if not wanted:
            continue
        if not sized:  # sizes are read now, only for the ROMs being synced
            listings[s["bucket"]] = inventory.stat(wanted)
        have = listings[s["bucket"]]
        dest = dest_of(s)
        disc_keys = discs_of(s)
        if disc_keys:  # discs a past sync left loose go where they belong rather than being downloaded again
            moved.update(downloads.hide_discs(dest, disc_dir, disc_keys, args.dry_run))
        for key in wanted:
            if key in have:
                try:
                    rom_jobs.append((key, s3.safe_join(dest, downloads.rom_rel(key, unzip, disc_dir, disc_keys)), have[key]))
                except ValueError as e:
                    print(ui.yellow(f"  ⚠️  skipping {e}"))
            else:
                missing.append(key)
    ui.report_missing(missing, "ROM(s)")
    # systems can share a folder (Onion: WS, NGP), so a folder's expected files are the union over all of them
    # a system with nothing to sync is always scanned, selected or not: whatever it has on the card is unwanted
    chosen_ids = {s["bucket"] for s in chosen}
    dropped_dests = {os.path.join(roms_dir, s["folders"][layout_name]) for s in dropped if s["folders"].get(layout_name)}
    # a system's rom_files are BIOS files that go in its ROM folder (MAME-style BIOS zips), kept while it has ROMs to sync
    dest_keys, dest_discs, dest_bios = defaultdict(list), defaultdict(set), defaultdict(set)
    for t in systems:
        dest_keys[dest_of(t)] += available(t)
        dest_discs[dest_of(t)].update(discs_of(t))
        if available(t) and not unzip:
            dest_bios[dest_of(t)].update(rom_bios_names(t))
    for dest in sorted({dest_of(s) for s in systems if s["bucket"] in chosen_ids or not available(s)} | dropped_dests):
        extras += downloads.find_extras(dest, dest_keys[dest], unzip, onion, disc_dir, dest_discs[dest], dest_bios[dest])

    # BIOS for every system with ROMs already on the card too, even when this sync doesn't touch that system
    bios_systems = chosen + [s for s in systems if s["bucket"] not in chosen_ids
                             and downloads.has_local_files(dest_of(s), onion, rom_bios_names(s))]
    # (bucket key, folder, path in it) of each BIOS file: in the BIOS folder, or in the ROM folder of a system with ROMs to sync
    bios_dests = {("BIOS/" + f, bios_dir, f) for s in bios_systems for f in s["bios"]["files"]}
    bios_dests |= {("BIOS/" + f, dest_of(s), os.path.basename(f))
                   for s in bios_systems if available(s) and not unzip for f in s["bios"].get("rom_files", [])}
    bios_keys = sorted({k for k, _, _ in bios_dests})
    bios_have = (inventory.stat(bios_keys) if s3.read_root() else inventory.files("BIOS/")) if bios_keys else {}
    bios_jobs = []
    for k, folder, rel in sorted(bios_dests):
        if k in bios_have:
            try:
                bios_jobs.append((k, s3.safe_join(folder, rel), bios_have[k]))
            except ValueError as e:
                print(ui.yellow(f"  ⚠️  skipping {e}"))
    ui.report_missing([k for k in bios_keys if k not in bios_have], "BIOS file(s)")
    # Android cards also get storage's os/android/APKs/ files (APKs, the Obtainium app list) in an APKs/ folder to install from
    apk_dir = os.path.join(base, "APKs")
    apk_jobs = ([(k, os.path.join(apk_dir, k[len(runtime.APKS_PREFIX):]), size) for k, size in sorted(inventory.files(runtime.APKS_PREFIX, sizes=False).items())
                 if not k.endswith("/")] if layout_name == "esde" else [])
    apk_jobs = downloads.with_sizes(apk_jobs)

    # Onion cards also get storage's os/onion/Themes/ folders in the card's Themes/
    themes_dir = layout.get("themes_dir")
    theme_jobs = []
    if themes_dir:
        for k, size in sorted(inventory.files(runtime.THEMES_PREFIX, sizes=False).items()):
            rel = k[len(runtime.THEMES_PREFIX):]
            if k.endswith("/") or os.path.basename(rel) == ".DS_Store":
                continue
            try:
                theme_jobs.append((k, s3.safe_join(os.path.join(base, themes_dir), rel), size))
            except ValueError as e:
                print(ui.yellow(f"  ⚠️  skipping {e}"))

    theme_jobs = downloads.with_sizes(theme_jobs)

    rom_todo, bios_todo = downloads.plan_downloads(rom_jobs, unzip, disc_dir), downloads.plan_downloads(bios_jobs)
    apk_todo = downloads.plan_downloads(apk_jobs)
    theme_todo = downloads.plan_downloads(theme_jobs)
    if args.dry_run:  # the real run moves these first, so they are already there
        rom_todo = [j for j in rom_todo if j[1] not in moved]
    elif moved:
        print(ui.dim(f"  📦 Moved {len(moved)} loose disc file(s) into {disc_dir}/"))
    summary = [f"{icon} {label}: {ui.bold(str(len(todo)))} to download ({ui.human_size(total_bytes(todo))}), "
               f"{len(jobs) - len(todo)} already present"
               for icon, label, todo, jobs, always in (("💿", "ROMs", rom_todo, rom_jobs, True), ("🧠", "BIOS", bios_todo, bios_jobs, True),
                                                       ("🤖", "Android", apk_todo, apk_jobs, False), ("🎨", "Themes", theme_todo, theme_jobs, False))
               if always or jobs]
    print("\n" + "\n".join(summary))
    if extras:
        print(f"🗑️  Local ROMs no longer in the selection: {ui.bold(str(len(extras)))}")
    es_dir = os.path.join(base, "ES-DE")
    scrapes = layout_name in scrape_plan.SCRAPE_LAYOUTS
    scraped = {}
    todo_all = rom_todo + bios_todo + apk_todo + theme_todo

    def build_plan(present):
        if not scraped:
            print("🖼️  Reading scraped data...")
            scraped["data"] = scrape_plan.load_scrape_data(chosen)
            scraped["rels"] = {s["bucket"]: [k.split("/", 1)[1] for k in available(s) if k in listings[s["bucket"]]]
                               for s in chosen}
        if unzip:  # a ROM that's extracted from its archive is on the card under another extension
            present = lambda path, exists=present: exists(path) or downloads.archive_extracted(path)  # noqa: E731
        return scrape_plan.build_scrape_plan(layout_name, chosen, scraped["data"], scraped["rels"], dest_of, es_dir, present, base)

    def frontend_step(dry_run):
        """Write the card's collections as the frontend's custom collections (ES-DE, Knulli)."""
        if layout_name not in frontend.FRONTEND_LAYOUTS:
            return
        entry = store.load_cards().get(card)
        entry = entry if isinstance(entry, dict) else {}

        def names(field):
            """The card's list field as its text items (anything else stored there is ignored)."""
            values = entry.get(field)
            return [v for v in values if isinstance(v, str)] if isinstance(values, list) else []
        by_id = {c["id"]: c for c in colls.load_collections()}
        card_colls = [by_id[i] for i in names("collections") if i in by_id]
        surprises = [x for x in entry.get("surprises") or () if isinstance(x, dict)
                     and isinstance(x.get("system"), str) and isinstance(x.get("bucket"), str)]
        if surprise.enabled(entry) and surprises:  # as saved now: the card editor may have changed them
            card_colls.append({"name": surprise.COLLECTION, "games": surprises})  # its art is added below
        owned = names("frontend_collections")
        if not card_colls and not owned:
            return
        coming = {(s["bucket"], downloads.rom_rel(k, False)) for s in chosen
                  for k in available(s) if k in listings[s["bucket"]]} if dry_run else set()

        def on_card(s, rel):
            return (s["bucket"], rel) in coming or os.path.exists(os.path.join(dest_of(s), rel))

        wanted = frontend.wanted_collections(layout_name, card_colls, systems, on_card)
        plan = frontend.plan_collections(layout_name, base, wanted, owned)
        arts = {frontend.safe_name(c["name"]): c["art"] for c in card_colls if c.get("art")}
        if surprise.COLLECTION in plan["enable"]:
            arts[surprise.COLLECTION] = themeart.SURPRISE_ART
        arts = {name: art for name, art in arts.items() if name in plan["enable"]}
        if dry_run:
            frontend.describe_collections(plan, layout_name)
            if arts:
                themeart.describe(layout_name, base, arts)
            return
        for warning in plan["warnings"]:
            ui.warn(warning)
        frontend.apply_collections(plan, layout_name, base)
        if plan["owned"] != owned:
            store.update_card(card, frontend_collections=plan["owned"])
        art = bool(arts) and themeart.install(layout_name, base, arts)
        if clean_card and (plan["writes"] or plan["deletes"] or art):
            clean._clean_root = base
        if plan["writes"]:
            print(ui.green(f"💖 Wrote {len(plan['writes'])} collection(s) for {layout['label']}"))

    capacity = budget.card_capacity(saved or {}) if surprise.enabled(saved or {}) else None
    if capacity:
        used = budget.card_usage(cardedit.card_entry(card, (device, layout_name)), systems).bytes
        if used > capacity:
            ui.warn(f"{card}'s picks take {cardedit.size_text(used)} of its {saved['size']}: "
                    f"{cardedit.size_text(used - capacity)} over")

    if args.dry_run:
        print(ui.yellow("\n🧪 Dry run — nothing downloaded or deleted"))
        plan_json = {
            "downloads": [{"kind": kind, "key": key, "path": path, "size": size or 0}
                          for kind, todo in (("rom", rom_todo), ("bios", bios_todo), ("android", apk_todo), ("theme", theme_todo)) for key, path, size in todo],
            "delete": list(extras), "missing": {"roms": missing, "bios": [k for k in bios_keys if k not in bios_have]}}
        for key, path, _ in todo_all:
            print(f"  {key} {ui.dim('→')} {path}")
        if unzip:
            pending = {j[1] for j in rom_todo} | set(chd.card_archives({dest_of(s) for s in chosen}))
            print(f"📦 Archives to extract: {len([p for p in pending if p.lower().endswith(external.ARCHIVE_EXTS)])}")
        for path in extras:
            print(f"  {ui.red('would delete')} {path}")
        stale_count = 0
        if scrapes:
            scrape_plan.describe_scrape_plan(build_plan(lambda path: True))
            stale_count = len(scrape_plan.stale_media(layout_name, manifest['systems'], roms_dir, es_dir, base))
            print(f"🧹 Media on the card for ROMs it doesn't have: {stale_count} file(s) to remove")
        frontend_step(True)
        if layout_name == "esde":
            clean.clean_android_media(base, card, True, args.ask)
        plan_json["stale_media"] = stale_count
        plan_json["totals"] = {"files": len(todo_all), "bytes": total_bytes(todo_all), "delete": len(extras),
                               "stale_media": stale_count, "missing": len(missing)}
        if args.json:
            ui.emit_json(plan_json)
        print(ui.bold(f"\n🧪 Would download {len(todo_all)} file(s) ({ui.human_size(total_bytes(todo_all))}), "
                      f"delete {len(extras)} local ROM(s) and {stale_count} media file(s); {len(missing)} listed ROM(s) not in storage"))
        return 0

    if extras:  # cleared first so the free space shown below is what the downloads really get
        delete_extras(extras)

    if todo_all:
        need = total_bytes(todo_all)
        free = free_space(base)
        size = (saved or {}).get("size")
        print(f"💾 Free on the card: {ui.human_size(free)}" + (f" ({size} card)" if size else ""))
        if need > free:
            print(ui.red(f"❌ Not enough space: {ui.human_size(need)} to download, {ui.human_size(free)} free"))
            if not ui.confirm("Try anyway?", default=False):
                print(ui.yellow("👋 Cancelled."))
                return 0
        if not ui.confirm(f"⬇️  Download {len(todo_all)} file(s) ({ui.human_size(need)})?"):
            print(ui.yellow("👋 Cancelled."))
            return 0

    if clean_card and todo_all:  # nothing downloaded means nothing to finalize
        clean._clean_root = base
    failures = []
    failed = downloads.run_downloads(rom_todo, "ROMs", "💿", roms_dir, failures) + downloads.run_downloads(bios_todo, "BIOS", "🧠", bios_dir, failures)
    failed += downloads.run_downloads(apk_todo, "Android", "🤖", apk_dir, failures)
    if theme_todo:
        failed += downloads.run_downloads(theme_todo, "Themes", "🎨", os.path.join(base, themes_dir), failures)
    for s in chosen:
        if disc_dir and available(s):
            m3u.prefix_playlists(dest_of(s), disc_dir)
    if unzip:
        # also archives already on the card (not just new downloads), e.g. from an interrupted run
        archives = sorted({j[1] for j in rom_todo} | set(chd.card_archives({dest_of(s) for s in chosen})))
        for path, error in chd.unzip_roms(archives):
            failed += 1
            failures.append((os.path.relpath(path, roms_dir), error))
            print(ui.red(f"  ❌ {os.path.relpath(path, roms_dir)}: {error}"))

    if layout_name in ("esde", "emudeck"):  # ES-DE launches an installed Vita game through its .psvita file
        for path, error in vita.add_psvita_files({dest_of(s) for s in chosen if s["bucket"] == "psvita"}):
            failed += 1
            failures.append((os.path.relpath(path, roms_dir), error))
            print(ui.red(f"  ❌ {os.path.relpath(path, roms_dir)}: {error}"))

    stale = []
    if scrapes:
        plan = build_plan(os.path.exists)
        scrape_plan.describe_scrape_plan(plan)
        if clean_card and (plan["jobs"] or plan["writes"] or plan["gamelists"]):
            clean._clean_root = base
        failed += scrape_plan.apply_scrape_plan(plan, base)
        stale = scrape_plan.stale_media(layout_name, manifest["systems"], roms_dir, es_dir, base)
    remove_stale_media(stale)
    for folder in scrape_plan.prune_empty_systems(layout_name, manifest["systems"], roms_dir):
        print(ui.green(f"🧹 Removed empty system folder {os.path.relpath(folder, base)}"))
    frontend_step(False)
    if layout_name == "esde":  # only Android cards have these folders; a Knulli card's "music" must stay
        clean.clean_android_media(base, card, False, args.ask)
    if failures:
        report_failures(failures)
    if not failed and not args.no_eject and usersettings.load_settings().get("eject", True) is not False:
        clean._eject_root = base  # after the card tidy, which still needs it mounted
    print(ui.green("\n🎉 Done!") if not failed else ui.red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0


def free_space(path):
    while not os.path.exists(path):
        path = os.path.dirname(path)
    return shutil.disk_usage(path).free

"""Download ROMs and BIOS files from the roms bucket."""
import argparse
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from . import __version__, chd, clean, commands, diff, downloads, edit, external, m3u, mirroring, picker, runtime, s3, scrape_files, scrape_plan, store, ui, upload, usersettings


SUBCOMMANDS = {  # name -> (usage, one-line summary)
    "sync": ("[CARD]", "download the ROMs, BIOS and scraped data for a card (this is what plain `sync-roms CARD` does)"),
    "games": ("edit|list|add|remove|full|sets|export|import", "edit the core game list or a card's extras, interactively or from scripts"),
    "cards": ("list|new|set|rename|delete", "list and manage the cards you've synced"),
    "devices": ("[ID]", "list the supported devices, or one device's systems"),
    "upload": ("roms [DIR] | scrapes [CARD]", "upload ROMs or a card's scraped data to the bucket"),
    "diff": ("[DIR]", "list the ROMs in only DIR or only the bucket, ignoring renames"),
    "clean": ("scrapes", "remove scrapes/ media and metadata for ROMs that aren't in the bucket"),
    "playlist": ("[DIR]", "create or fix the .m3u playlist of every multi-disc game"),
    "convert": ("[DIR]", "unzip archives and convert disc images to verified .chd"),
    "tools": ("install", "brew install the 7z and chdman that `convert` needs"),
    "mirror": ("[DIR] | use DIR | clear", "make or refresh a local copy of everything your lists reference"),
    "config": ("show|path", "show the effective settings and where each comes from"),
    "doctor": ("", "check the AWS profile, bucket access, tools and your data files"),
    "check": ("", "validate games.json, cards.json, the device overlay and the sets"),
    "completion": ("bash|zsh|fish", "print a shell completion script"),
}

TOPICS = {
    "sync": """
  sync-roms [sync] [CARD] [--dry-run] [--ask] [--yes] [--device ID|full] [--layout NAME] [--systems IDS|all] [--no-clean]

  CARD is the card or folder root (default: the current directory); the chosen firmware decides the folders inside
  it (ES-DE ROMs/ BIOS/, Knulli roms/ bios/, Onion Roms/ BIOS/). Missing folders are created after you confirm.

  FLOW
   1. Pick a device (its recommended systems come from device-systems.json plus your overlay) or Full, then its
      firmware. Remembered per card folder name and used without asking next time; --ask confirms it first.
      --device/--layout set it without the picker (and save it).
   2. Toggle systems (--systems a,b or --systems all skips the picker).
   3. Totals and free space are shown and you confirm; ROMs download, then BIOS.
   4. Scraped data for the chosen systems' games is installed from the bucket's scrapes/ folder, then media on the
      card for ROMs it doesn't have is removed.
   5. Local ROMs no longer in a chosen system's list are listed and, after you confirm (default no), deleted.
      Other systems' folders and BIOS are never touched.

  --dry-run   show what would be downloaded and deleted, change nothing
  --yes       answer every prompt with its default (a default-no prompt, like deleting files, stays no)
  --no-clean  skip the end-of-run card tidy (.metadata_never_index, .fseventsd, dot_clean)

  A finished run (not --dry-run) creates .metadata_never_index in CARD, empties its .fseventsd, and on a Mac runs
  dot_clean (falling back to sudo mdutil, which asks for your password). ES-DE: files in the Android media folders
  are removed and a .nomedia added after asking once per card name (the answer is remembered; --ask confirms it).
  Picker keys: ↑/↓ j/k move, space/tab toggle, a all on, n all off, e show 0-ROM systems, g edit games, enter go, esc/q cancel.
""",
    "games": """
  sync-roms games edit                        interactive editor (core list, card extras, device systems)
  sync-roms games list [--card NAME] [--json]
  sync-roms games add SYSTEM KEY... [--card NAME] [-n]      KEY: file name, SYSTEM/file key, or a glob like 'Mario*'
  sync-roms games remove SYSTEM KEY... [--card NAME] [-n]
  sync-roms games full SYSTEM on|off [--card NAME] [-n]
  sync-roms games sets list | add ID | remove ID [--card NAME] [-n]
  sync-roms games export [--card NAME]        one SYSTEM/file per line (full systems as 'SYSTEM/*')
  sync-roms games import FILE [--card NAME] [-n]            add the games in such a file

  Without --card the core list (every card) is changed; with it, that card's extras. Lists are saved in ~/.sync-roms/
  (games.json, cards.json) with the previous version kept as .bak. Removing only drops a game from the list.
  In the editor: Tab toggles a row, ^A all shown, ^R reverts the list, ^O cycles all/on/changed, ^F toggles a whole set or system.
""",
    "cards": """
  sync-roms cards list [--json]
  sync-roms cards new NAME --device ID|full --layout NAME
  sync-roms cards set NAME [--device ID|full] [--layout NAME]
  sync-roms cards rename OLD NEW
  sync-roms cards delete NAME [--yes]

  A card is a folder name (the card root's basename) with a remembered device, firmware and extra games.
""",
    "devices": """
  sync-roms devices [ID] [--json]

  Without an ID: every device with its chip and system count. With one: its firmwares, note and systems.
""",
    "upload": """
  sync-roms upload roms [DIR] [--replace] [--dry-run]    upload the ROMs in DIR (default: current directory) to the bucket folder of a system you pick
  sync-roms upload scrapes [CARD] [--dry-run]            upload CARD/ES-DE scraped data to the bucket's scrapes/ folder, merging with what's there

  The system is guessed from the folder name; same-size files are skipped, a different size overwrites after you confirm.
  --replace makes the bucket folder match DIR: renamed files are moved by content, and left-over bucket files are listed
  so you pick which to delete. Uploads use the write profile (ROMS_WRITE_PROFILE, default 'roms').
""",
    "diff": """
  sync-roms diff [DIR]

  Lists the ROMs in only one of DIR and the bucket folder of a system you pick. Same path and size is the same file;
  the rest are matched by content (the CRCs inside zips).
""",
    "clean": """
  sync-roms clean scrapes [--dry-run]

  Removes scrapes/ media and metadata for ROMs that aren't in the bucket at all (asks first).
""",
    "playlist": """
  sync-roms playlist [DIR] [--dry-run]

  Creates or fixes the .m3u of every multi-disc game ("Name (Disc 1).chd", "Name (Disc 2).chd") in DIR and its
  subfolders. Playlists whose files are all missing are deleted (asks first). Local only. (Old name: --m3u)
""",
    "convert": """
  sync-roms convert [DIR] [--dry-run]

  Unzips (7z) every .zip/.7z and converts each disc image (.cue, .gdi, .toc, .iso) to a verified .chd (Xbox .iso to xiso),
  per the chd setting of the system whose folder it is in. Archives and images are removed once their chd verifies,
  then the .m3u playlists are fixed. Needs 7z, chdman and, for Xbox, extract-xiso (see `tools install`). (Old names: --cd, --chd)
""",
    "tools": """
  sync-roms tools install

  brew install the 7z (sevenzip) and chdman (rom-tools) that `convert` needs, and say how to build extract-xiso.
""",
    "mirror": """
  sync-roms mirror [DIR] [--dry-run]     make or refresh a local copy of everything the lists reference (no DIR: the saved mirror)
  sync-roms mirror use DIR               refresh DIR, then save it so every sync refreshes it first and copies from it
  sync-roms mirror clear                 forget the saved mirror (its files stay)

  Files no longer referenced are deleted (after confirming when it is a lot); nothing is deleted if a download failed.
""",
    "config": """
  sync-roms config show      the effective bucket, endpoint, profiles and mirror, and where each came from
  sync-roms config path      the data folder
""",
    "doctor": """
  sync-roms doctor

  Checks the AWS profile and bucket access, the tools `convert` needs, and that your data files parse.
""",
    "check": """
  sync-roms check [--bucket-keys]

  Validates games.json, cards.json, device-systems.json and the sets (built-in and ~/.sync-roms/sets): bad JSON,
  unknown systems, devices and sets. Exits 1 if anything is wrong.
  --bucket-keys also lists the bucket (read-only profile) and reports every game or set file it doesn't have.
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
{ui.bold('🎮 sync-roms')} — download ROMs and BIOS files from your S3 bucket

{ui.bold('USAGE')}
  {ui.green('sync-roms')} [{ui.cyan('CARD')}]                 sync a card (same as `sync-roms sync CARD`)
  {ui.green('sync-roms')} {ui.cyan('COMMAND')} [options]      one of the commands below; `sync-roms COMMAND --help` explains it

{ui.bold('COMMANDS')}
{rows}

{ui.bold('GLOBAL OPTIONS')}
  {ui.yellow('-n, --dry-run')}   show what would happen, change nothing (commands that can't honor it refuse it)
  {ui.yellow('-y, --yes')}       answer prompts with their default (deleting stays "no")
  {ui.yellow('--quiet')}         print only errors, warnings and --json data (prompts go to stderr)      {ui.yellow('--verbose')}   also print the effective settings
  {ui.yellow('--json')}          machine-readable output for devices, diff and `sync --dry-run` (use --systems with --device/--layout to skip the pickers)
  {ui.yellow('--profile P')} {ui.yellow('--write-profile P')} {ui.yellow('--bucket B')} {ui.yellow('--endpoint URL')}   override those settings for this run
  {ui.yellow('-a, --ask')}       sync: confirm the saved device/firmware and Android media choice instead of using it silently
  {ui.yellow('--version')}       print the version      {ui.yellow('-h, --help')}   this screen

{ui.bold('ENVIRONMENT')}
  {ui.yellow('ROMS_BUCKET')}  {ui.yellow('ROMS_ENDPOINT')}  {ui.yellow('ROMS_PROFILE')} (default roms-readonly)  {ui.yellow('ROMS_WRITE_PROFILE')} (default roms)
  override settings.json "bucket", "endpoint", "profile", "write_profile"; the flags above override these. {ui.yellow('NO_COLOR')} / {ui.yellow('FORCE_COLOR')} control colors.

{ui.bold('EXIT CODES')}
  0 done (or nothing to do, or you declined)   1 some files failed   2 bad usage   3 setup problem (credentials, bucket, tools, bad data file)   130 interrupted

{ui.bold('EXAMPLES')}
  sync-roms /Volumes/SD                          sync the card
  sync-roms sync /Volumes/SD --device rg35xx-sp --layout knulli --systems all --yes --dry-run
  sync-roms games add gba 'Metroid*' --card SD   add games to a card's extras
  sync-roms upload roms ~/roms/gba               upload ROMs to the bucket

  {ui.dim('The old flags (--edit, --upload, --upload-scrapes, --clean-scrapes, --m3u, --cd, --install-tools, --mirror,')}
  {ui.dim('--use-mirror, --clear-mirror, --devices) still work. A card folder named like a command: write ./edit.')}
"""


def check_dir(path, label):
    """Fail early if `path` can't be used or created. Returns True if it must be created."""
    if os.path.exists(path):
        if not os.path.isdir(path):
            raise SystemExit(ui.red(f"❌ {label} {path} exists but is not a directory"))
        if not os.access(path, os.W_OK | os.X_OK):
            raise SystemExit(ui.red(f"❌ No write permission for {label} {path}"))
        return False
    parent = os.path.dirname(path)
    while not os.path.exists(parent):
        parent = os.path.dirname(parent)
    if not os.path.isdir(parent) or not os.access(parent, os.W_OK | os.X_OK):
        raise SystemExit(ui.red(f"❌ Can't create {label} {path}: no write permission in {parent}"))
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
    finally:
        clean.clean_dirs()


def list_devices(args=None):
    """Print a table of the devices (name, chip, number of recommended systems), or one device's details given its id."""
    manifest = store.load_manifest()
    devices = manifest["devices"]
    return commands.show_devices(devices, manifest["systems"], getattr(args, "device_id", None), getattr(args, "json", False))


class Parser(argparse.ArgumentParser):
    def error(self, message):
        ui.fail(f"{message}\n   Try 'sync-roms --help'.", 2)


# subcommand -> the legacy flags it stands for. {rest} are its remaining arguments.
LEGACY = {
    ("sync",): [], ("devices",): ["--devices"], ("diff",): ["--diff"], ("playlist",): ["--m3u"], ("convert",): ["--cd"],
    ("tools", "install"): ["--install-tools"], ("clean", "scrapes"): ["--clean-scrapes"],
    ("upload", "roms"): ["--upload"], ("upload", "scrapes"): ["--upload-scrapes"],
    ("mirror", "use"): ["--use-mirror"], ("mirror", "clear"): ["--clear-mirror"], ("mirror",): ["--mirror"],
    ("games", "edit"): ["--edit"],
}
BOOL_FLAGS = {"-n", "--dry-run", "-y", "--yes", "-a", "--ask"}
PLAIN_FLAGS = BOOL_FLAGS | {"--replace", "--json", "--no-clean"}


def translate(argv):
    """Rewrite `sync-roms COMMAND ...` into the flag form the rest of the code reads. Global flags may come first."""
    i = 0
    while i < len(argv) and argv[i] in BOOL_FLAGS:
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
            n = 0  # plain flags before the mode's value (`diff -n /x`) move behind it
            while n < len(tail) and tail[n] in PLAIN_FLAGS:
                n += 1
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
    ap.add_argument("--systems")
    ap.add_argument("--no-clean", action="store_true")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    return ap


def check_modes(args):
    """Refuse flag combinations that would silently do nothing. Returns the active mode's name (None for a plain sync)."""
    modes = [name for name, on in (
        ("--edit", args.edit), ("--upload", args.upload is not None), ("--diff", args.diff is not None),
        ("--upload-scrapes", args.upload_scrapes), ("--clean-scrapes", args.clean_scrapes),
        ("--mirror", args.mirror is not None), ("--use-mirror", bool(args.use_mirror)), ("--clear-mirror", args.clear_mirror),
        ("--m3u", args.m3u is not None), ("--cd", args.chd is not None), ("--install-tools", args.install_tools),
        ("--devices", args.devices)) if on]
    if len(modes) > 1:
        ui.fail(f"{' and '.join(modes[:2])} can't be combined: use one command at a time", 2)
    mode = modes[0] if modes else None
    if args.replace and mode != "--upload":
        ui.fail("--replace only works with `upload roms` (--upload)", 2)
    if args.dry_run and mode in ("--edit", "--install-tools", "--clear-mirror", "--devices"):
        ui.fail(f"--dry-run has no effect on {mode}", 2)
    if args.ask and mode:
        ui.fail(f"--ask only applies to syncing a card, not {mode}", 2)
    if (args.device or args.layout or args.systems or args.no_clean) and mode:
        ui.fail(f"--device, --layout, --systems and --no-clean only apply to syncing a card, not {mode}", 2)
    if args.base_dir and mode not in (None, "--upload-scrapes", "--clean-scrapes"):
        ui.fail(f"{mode} doesn't take a card folder ({args.base_dir!r}); give the directory right after the command", 2)
    if args.device_id and mode != "--devices":
        ui.fail("a device id only applies to `devices`", 2)
    if args.json and not (mode in ("--devices", "--diff") or (mode is None and args.dry_run)):
        ui.fail("--json only applies to `devices`, `diff` and `sync --dry-run`", 2)
    if args.system and mode != "--diff":
        ui.fail("--system only applies to `diff`", 2)
    return mode


GLOBAL_VALUE_FLAGS = {"--profile": "profile", "--write-profile": "write_profile", "--bucket": "bucket", "--endpoint": "endpoint"}
DATA_COMMANDS = {("devices",), ("completion",), ("games", "list"), ("games", "export"), ("cards", "list"), ("config", "path")}


def extract_globals(argv):
    """Remove --profile/--write-profile/--bucket/--endpoint (set in runtime.OVERRIDES) and --quiet/--verbose from argv.
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
    if lead < len(argv) and argv[lead] in commands.COMMANDS and argv[lead:lead + 2] != ["games", "edit"]:
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
    if args.devices:
        return list_devices(args)
    if mode in ("--m3u", "--cd", "--install-tools"):
        if args.install_tools:
            return external.install_tools_command()
        return chd.chd_command(args) if args.chd is not None else m3u.m3u_command(args)
    usersettings.ensure_bucket()
    if args.upload is not None:
        return upload.upload_command(args)
    if args.diff is not None:
        return diff.diff_command(args)
    if args.mirror is not None or args.use_mirror or args.clear_mirror:
        return mirroring.mirror_command(args)
    if args.edit or args.upload_scrapes or args.clean_scrapes:
        code = edit.edit_manifest() if args.edit else scrape_files.upload_scrapes(args) if args.upload_scrapes else scrape_files.clean_scrapes(args)
        mirror = usersettings.load_settings().get("mirror")
        if mirror and not code and not args.dry_run:  # pick up the games just added
            print()
            mirroring.use_mirror(mirror, False)
        return code
    base = os.path.abspath(os.path.expanduser(args.base_dir or os.getcwd()))

    print(ui.bold("🎮 sync-roms") + ui.dim(f"  s3://{runtime.BUCKET}  profile={runtime.PROFILE}"))
    if usersettings.load_settings().get("mirror"):
        mirroring.use_mirror(usersettings.load_settings()["mirror"], args.dry_run)
    print("📄 Fetching manifests...")
    card = os.path.basename(base) or base
    manifest = store.load_manifest([card])
    systems = manifest["systems"]
    devices, layouts = manifest["devices"], manifest["layouts"]
    saved = store.load_cards().get(card)
    dirs = None
    setup = picker.saved_setup(saved, devices, layouts)
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
            return 0
        if not args.dry_run:
            store.save_card(card, device, layout_name)
    layout = layouts[layout_name]
    unzip = layout.get("unzip", False)  # ROMs go in flat and unzipped (Slot)
    roms_dir, bios_dir = dirs
    clean_card = not args.dry_run and not args.no_clean
    if device:
        wanted_ids = set(device["systems"])
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
    listings, state = {}, {}

    def available(s):
        return store.available_keys(s, listings[s["bucket"]])

    def sizes(s):
        """(bytes still to download, total bytes) for a system's ROMs."""
        have, need, total = listings[s["bucket"]], 0, 0
        for k in available(s):
            size = have.get(k, 0)
            try:
                path = s3.safe_join(os.path.join(roms_dir, s["folders"][layout_name]), downloads.rom_rel(k, unzip))
            except ValueError:
                continue
            total += size
            if downloads.plan_downloads([(k, path, size)], unzip):
                need += size
        return need, total

    while True:
        todo = [s for s in systems if not listings.get(s["bucket"])]
        with ThreadPoolExecutor(runtime.WORKERS) as ex:
            listings.update(zip((s["bucket"] for s in todo),
                                ex.map(lambda s: s3.list_sizes(s["bucket"] + "/")
                                       if s.get("full_system") or store.listed(s) else {}, todo)))
        rows = [(f"{s['name']}  ({len(available(s))} roms)", bool(available(s)), *sizes(s)) for s in systems]
        present = [i for i, s in enumerate(systems)
                   if available(s) and (device or downloads.has_local_files(os.path.join(roms_dir, s["folders"][layout_name])))]
        if args.systems:
            chosen = commands.systems_from_flag(args.systems, systems, available)
            break
        saved_idx = [i for i, s in enumerate(systems) if s["bucket"] in (saved or {}).get("systems", ())]
        if args.yes and saved_idx and not state:  # --yes with a saved selection: no picker
            chosen = saved_idx
            break
        chosen = picker.pick_systems(rows, saved_idx if saved_idx and not state else present, state, editable=not args.dry_run)
        if not isinstance(chosen, tuple):
            if chosen and not args.dry_run:
                store.update_card(card, systems=[systems[i]["bucket"] for i in chosen])
            break
        action, row = chosen
        if action == "games":  # the same list --edit changes for this card
            if edit.edit_card_system(card, systems[row]["bucket"], (device, layout_name)):
                state["sel"][row] = True
        elif ui.confirm(f"🧹 Clear {card}'s own games? (the core list stays)", default=False):
            store.update_card(card, games={})
            state["sel"] = [False] * len(systems)
        systems = reload_systems()
    if chosen is None:
        print(ui.yellow("👋 Cancelled."))
        return 0
    if not chosen:
        print(ui.yellow("👋 Nothing selected."))
        return 0
    chosen = [systems[i] for i in chosen]
    print(ui.bold(f"\n🔎 Checking {len(chosen)} system(s) against the bucket..."))

    def dest_of(s):
        return os.path.join(roms_dir, s["folders"][layout_name])

    rom_jobs, missing, extras = [], [], []
    for s in chosen:
        wanted = available(s)
        if not wanted:
            continue
        have = listings[s["bucket"]]
        dest = dest_of(s)
        for key in wanted:
            if key in have:
                try:
                    rom_jobs.append((key, s3.safe_join(dest, downloads.rom_rel(key, unzip)), have[key]))
                except ValueError as e:
                    print(ui.yellow(f"  ⚠️  skipping {e}"))
            else:
                missing.append(key)
    ui.report_missing(missing, "ROM(s)")
    # systems can share a folder (Onion: WS, NGP), so a folder's expected files are the union over all of them
    for dest in sorted({dest_of(s) for s in chosen if available(s)}):
        extras += downloads.find_extras(dest, [k for t in systems if dest_of(t) == dest for k in available(t)], unzip)

    bios_keys = sorted({"BIOS/" + f for s in chosen for f in s["bios"]["files"]})
    bios_have = s3.list_sizes("BIOS/") if bios_keys else {}
    bios_jobs = []
    for k in bios_keys:
        if k in bios_have:
            try:
                bios_jobs.append((k, s3.safe_join(bios_dir, k[len("BIOS/"):]), bios_have[k]))
            except ValueError as e:
                print(ui.yellow(f"  ⚠️  skipping {e}"))
    ui.report_missing([k for k in bios_keys if k not in bios_have], "BIOS file(s)")

    rom_todo, bios_todo = downloads.plan_downloads(rom_jobs, unzip), downloads.plan_downloads(bios_jobs)
    print(f"\n💿 ROMs: {ui.bold(str(len(rom_todo)))} to download "
          f"({ui.human_size(sum(j[2] or 0 for j in rom_todo))}), "
          f"{len(rom_jobs) - len(rom_todo)} already present")
    print(f"🧠 BIOS: {ui.bold(str(len(bios_todo)))} to download "
          f"({ui.human_size(sum(j[2] or 0 for j in bios_todo))}), "
          f"{len(bios_jobs) - len(bios_todo)} already present")
    if extras:
        print(f"🗑️  Local ROMs no longer in the selection: {ui.bold(str(len(extras)))}")
    es_dir = os.path.join(base, "ES-DE")
    scrapes = layout_name in scrape_plan.SCRAPE_LAYOUTS
    scraped = {}

    def build_plan(present):
        if not scraped:
            print("🖼️  Reading scraped data...")
            scraped["data"] = scrape_plan.load_scrape_data(chosen, layout_name == "esde")
            scraped["rels"] = {s["bucket"]: [k.split("/", 1)[1] for k in available(s) if k in listings[s["bucket"]]]
                               for s in chosen}
        if unzip:  # a ROM that's extracted from its archive is on the card under another extension
            present = lambda path, exists=present: exists(path) or downloads.archive_extracted(path)  # noqa: E731
        return scrape_plan.build_scrape_plan(layout_name, chosen, *scraped["data"], scraped["rels"], dest_of, es_dir, present, base)

    if args.dry_run:
        print(ui.yellow("\n🧪 Dry run — nothing downloaded or deleted"))
        plan_json = {
            "downloads": [{"kind": kind, "key": key, "path": path, "size": size or 0}
                          for kind, todo in (("rom", rom_todo), ("bios", bios_todo)) for key, path, size in todo],
            "delete": list(extras), "missing": {"roms": missing, "bios": [k for k in bios_keys if k not in bios_have]}}
        for key, path, _ in rom_todo + bios_todo:
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
        if layout_name == "esde":
            clean.clean_android_media(base, card, True, args.ask)
        todo_all = rom_todo + bios_todo
        plan_json["stale_media"] = stale_count
        plan_json["totals"] = {"files": len(todo_all), "bytes": sum(j[2] or 0 for j in todo_all), "delete": len(extras),
                               "stale_media": stale_count, "missing": len(missing)}
        if args.json:
            ui.emit_json(plan_json)
        print(ui.bold(f"\n🧪 Would download {len(todo_all)} file(s) ({ui.human_size(sum(j[2] or 0 for j in todo_all))}), "
                      f"delete {len(extras)} local ROM(s) and {stale_count} media file(s); {len(missing)} listed ROM(s) not in the bucket"))
        return 0

    todo_all = rom_todo + bios_todo
    if todo_all:
        need = sum(j[2] or 0 for j in todo_all)
        free = free_space(base)
        print(f"💾 Free on the card: {ui.human_size(free)}")
        if need > free:
            print(ui.red(f"❌ Not enough space: {ui.human_size(need)} to download, {ui.human_size(free)} free"))
            if not ui.confirm("Try anyway?", default=False):
                return 1
        if not ui.confirm(f"⬇️  Download {len(todo_all)} file(s) ({ui.human_size(need)})?"):
            print(ui.yellow("👋 Cancelled."))
            return 0

    if clean_card and todo_all:  # nothing downloaded means nothing to finalize
        clean._clean_root = base
    failures = []
    failed = downloads.run_downloads(rom_todo, "ROMs", "💿", roms_dir, failures) + downloads.run_downloads(bios_todo, "BIOS", "🧠", bios_dir, failures)
    if unzip:
        # also archives already on the card (not just new downloads), e.g. from an interrupted run
        archives = sorted({j[1] for j in rom_todo} | set(chd.card_archives({dest_of(s) for s in chosen})))
        for path, error in chd.unzip_roms(archives):
            failed += 1
            failures.append((os.path.relpath(path, roms_dir), error))
            print(ui.red(f"  ❌ {os.path.relpath(path, roms_dir)}: {error}"))

    if extras and failed:
        print(ui.yellow(f"\n⚠️  Keeping the {len(extras)} local ROM(s) no longer in the selection: {failed} download(s) failed"))
    elif extras:  # only after the downloads worked, so a failed run never leaves the card with fewer games
        print(ui.bold(f"\n🗑️  {len(extras)} local ROM(s) are no longer in the selection"))
        for path in extras[:10]:
            print(ui.dim(f"     {path}"))
        if len(extras) > 10:
            print(ui.dim(f"     … and {len(extras) - 10} more"))
        answer = ui.choose(f"Delete these {len(extras)} local file(s)?", "ynl", "n", "y yes · n no · l list all")
        while answer == "l":
            for path in extras:
                print(ui.dim(f"     {path}"))
            answer = ui.choose(f"Delete these {len(extras)} local file(s)?", "yn", "n")
        if answer == "y":
            for path in extras:
                os.remove(path)
            print(ui.green(f"  🧹 Deleted {len(extras)} file(s)"))
        else:
            print(ui.yellow("  ↩️  Keeping them"))

    stale = []
    if scrapes:
        plan = build_plan(os.path.exists)
        scrape_plan.describe_scrape_plan(plan)
        if clean_card and (plan["jobs"] or plan["extras"] or plan["writes"] or plan["gamelists"]):
            clean._clean_root = base
        failed += scrape_plan.apply_scrape_plan(plan, base)
        stale = scrape_plan.stale_media(layout_name, manifest["systems"], roms_dir, es_dir, base)
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
    if layout_name == "esde":  # only Android cards have these folders; a Knulli card's "music" must stay
        clean.clean_android_media(base, card, False, args.ask)
    if failures:
        print(ui.red(f"\n❌ {len(failures)} file(s) failed:"))
        for key, reason in failures[:20]:
            print(f"   {key}: {ui.dim(reason)}")
        if len(failures) > 20:
            print(ui.dim(f"   … and {len(failures) - 20} more"))
        print(ui.dim("   Files already downloaded are skipped, so run the same command again to retry just these."))
    print(ui.green("\n🎉 Done!") if not failed else ui.red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0


def free_space(path):
    while not os.path.exists(path):
        path = os.path.dirname(path)
    return shutil.disk_usage(path).free

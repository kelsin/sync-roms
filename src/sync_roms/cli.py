#!/usr/bin/env python3
"""Download ROMs and BIOS files from the roms bucket."""
import argparse
import os
import signal
import sys
from concurrent.futures import ThreadPoolExecutor

from . import chd, clean, diff, downloads, edit, external, m3u, mirroring, picker, runtime, s3, scrape_files, scrape_plan, store, ui, upload, usersettings


def help_text():
    return f"""
{ui.bold('🎮 sync-roms')} — download ROMs and BIOS files from your S3 bucket

{ui.bold('USAGE')}
  {ui.green('sync-roms')} [{ui.yellow('--dry-run')}] [{ui.cyan('BASE_DIR')}]   {ui.dim('(no folder: BASE_DIR is the current directory)')}

{ui.bold('ARGUMENTS')}
  {ui.cyan('BASE_DIR')}   📦 the card or folder root. The chosen layout decides the folders inside it
              {ui.dim('(ES-DE ROMs/ BIOS/, Knulli roms/ bios/, Onion Roms/ BIOS/)')}

  Missing folders are created after you confirm; if they can't be created
  (no permission) the script stops before asking.

{ui.bold('OPTIONS')}
  {ui.yellow('-n, --dry-run')}   show what would be downloaded, download nothing
  {ui.yellow('-e, --edit')}      ✏️  add/remove games in the core list (every card) or a card's extras, by system or set (type to filter);
                      {ui.yellow('^F')} toggles a whole set or system. {ui.dim('(no folders needed; saves ~/.sync-roms/games.json and cards.json)')}
  {ui.yellow('-a, --ask')}           ❓ confirm the saved settings (device and layout, Android media folders) instead of using them silently;
                      answering no asks the question again and saves the new answer
  {ui.yellow('-u, --upload-scrapes')} [{ui.cyan('BASE_DIR')}]   ☁️  upload BASE_DIR/ES-DE scraped data (metadata, media, themes, collections,
                      settings) to the bucket's scrapes/ folder, merging with what's there
                      {ui.dim('(only the safe-to-share metadata fields are kept; uploads with the ROMS_WRITE_PROFILE profile)')}
  {ui.yellow('--upload')} [{ui.cyan('DIR')}]   ☁️  upload the ROMs in DIR (no DIR: the current directory) and its subfolders to the bucket folder of a system you pick
                      {ui.dim('(the system is guessed from the folder name; files with the same size are skipped, a different size overwrites after you confirm;')}
                      {ui.dim('uploads in parallel, several requests per CPU core, with the ROMS_WRITE_PROFILE profile; works with --dry-run)')}
  {ui.yellow('--replace')}   {ui.dim('with --upload: make the bucket folder match DIR — renamed files are moved in the bucket by content, new and changed ones uploaded,')}
                      {ui.dim('and the bucket files left over (not renames) are listed so you pick which to delete and which to keep')}
  {ui.yellow('--diff')} [{ui.cyan('DIR')}]   🔍 list the ROMs in only one of DIR (no DIR: the current directory) and the bucket folder of a system you pick, ignoring renames
                      {ui.dim('(same path and size is the same file; the rest are matched by content: the CRCs inside zips, read from the zip index of just those files)')}
  {ui.yellow('-c, --clean-scrapes')}   🧹 remove scrapes/ media and metadata for ROMs that aren't in the bucket at all (asks first, no folder needed)
  {ui.yellow('--m3u')} [{ui.cyan('DIR')}]   💿 create or fix the .m3u playlist of every multi-disc game ("Name (Disc 1) (Extra).chd", "Name (Disc 2).chd") in DIR
                      and its subfolders (no DIR: the current directory); playlists whose files are all missing are deleted (asks first),
                      ones with the wrong or some missing discs are rewritten, and ones with the right discs under another name are renamed {ui.dim('(local only; works with --dry-run)')}
  {ui.yellow('--chd')} [{ui.cyan('DIR')}]   📀 unzip (7z) every .zip/.7z and convert each disc image (.cue, .gdi, .toc, .iso) to a verified .chd, per the chd setting of the
                      system whose folder it is in (DIR can be one system folder or hold several; no DIR: the current directory); archives and
                      images are removed once their chd verifies, then the .m3u playlists are fixed (always, even with nothing to convert); files convert in parallel, up to one per CPU core, with a progress bar. GameCube and Wii archives are only unzipped
                      {ui.dim('(needs 7z and chdman, see --install-tools; works with --dry-run)')}
  {ui.yellow('--install-tools')}   🍺 brew install the 7z (sevenzip) and chdman (rom-tools) that --chd needs, whichever are missing
  {ui.yellow('--mirror')} [{ui.cyan('DIR')}]   🪞 make or refresh a local copy of everything the game lists reference (ROMs, BIOS, scraped data); files that are
                      no longer referenced are deleted, a rerun with nothing changed downloads nothing (no DIR: the saved mirror)
  {ui.yellow('--use-mirror')} {ui.cyan('DIR')}   🪞 --mirror DIR, then save DIR so every sync refreshes it first and copies from it instead of the bucket
  {ui.yellow('--clear-mirror')}   forget the saved mirror (its files stay)
  {ui.yellow('--devices')}       📋 list the supported devices with their chip and how many systems each one gets, then exit
  {ui.yellow('-h, --help')}      show this screen

  {ui.dim('When it finishes (not on --dry-run), a .metadata_never_index file is created in BASE_DIR and its .fseventsd folder is emptied and given a no_log file (any OS); on a Mac, dot_clean then runs on BASE_DIR.')}
  {ui.dim('ES-DE layout: files in the Android media folders (Alarms, DCIM, Download, Music, Pictures...) are removed and a .nomedia added')}
  {ui.dim('to each, after asking once per card name; the answer (always/never) is saved in the user data folder and used without asking (--ask confirms it).')}
  {ui.dim('If dot_clean fails, Spotlight is turned off for BASE_DIR with sudo mdutil (asks for your password) and dot_clean is retried.')}

{ui.bold('FLOW')}
  1️⃣  Pick a device (its recommended systems come from the repo's device-systems.json, plus your add/remove overlay), or {ui.bold('Full')} (every system),
      then its firmware (ES-DE, Knulli, muOS, Onion or Slot; the firmware decides the folder layout, and a device with one firmware isn't asked). Type to filter, enter continues, esc goes back.
      The choice is remembered per BASE_DIR folder name (in the user data folder) and used without asking next
      time. With --ask it is confirmed first; answer n to pick again.
  2️⃣  Toggle systems on/off (for a device, its recommended systems start on; otherwise systems whose folder already has files start on, the rest off; systems with no ROMs are hidden, press e shows them last)
  3️⃣  ROMs download, then BIOS for the chosen systems
  4️⃣  Scraped data (media, descriptions...) for the chosen systems' games is installed from the bucket's scrapes/ folder
      for the firmware: ES-DE (ES-DE/ folder), Knulli (images/videos/manuals and gamelist.xml), Onion (Imgs/ and
      miyoogamelist.xml), muOS (catalogue box/preview/text) or Slot (cart labels). ES-DE also gets its themes, collections and the shared settings every time.
      Then media on the card for ROMs the card doesn't have is removed, for every system, no questions asked.

{ui.bold('PICKER KEYS')}
  {ui.yellow('↑/↓ j/k')} move   {ui.yellow('PgUp/PgDn')} page   {ui.yellow('space/tab')} toggle
  {ui.yellow('a')} all on   {ui.yellow('n')} all off   {ui.yellow('e')} show/hide 0-ROM systems
  {ui.yellow('enter')} confirm   {ui.yellow('q')} quit

{ui.bold('ENVIRONMENT')}
  {ui.yellow('ROMS_BUCKET')}    S3 bucket name (overrides settings.json "bucket")
  {ui.yellow('ROMS_ENDPOINT')}  custom S3 endpoint URL (overrides settings.json "endpoint"; default: AWS)
  {ui.yellow('ROMS_PROFILE')}   aws profile to use (overrides settings.json "profile"; default: roms-readonly)
  {ui.yellow('ROMS_WRITE_PROFILE')}   aws profile used to upload and clean scrapes (overrides "write_profile"; default: roms)
  {ui.yellow('NO_COLOR')}       disable colors

{ui.bold('NOTES')}
  ⚡ Files already present locally with the same size are skipped.
  🗑️  Local ROMs no longer in a chosen system's list are listed and, after you
     confirm (default no), deleted. Other systems' folders and BIOS are never touched.
     Frontend files are ignored: dotfiles, ES-DE systeminfo.txt/noload.txt, Knulli _info.txt,
     gamelist.xml and images/ videos/ manuals/ folders, Onion miyoogamelist.xml and Imgs/, Thumbs.db.
  📄 games.json lives in ~/.sync-roms/ (copied from the repo's version on first run) and is never read from the
     bucket. It is the core list every card gets; a card's own extra games are saved in cards.json and add to it.
     A list can also name whole sets: "sets": ["mario", "zelda"]. Optional ~/.sync-roms/device-systems.json adjusts a device's recommended systems:
     {{"miyoo-flip-v2": {{"add": ["psx"], "remove": ["gba"]}}}}
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
    if ask and not ui.confirm("Continue with these folders?"):
        return None
    for path in sorted(missing):
        if dry_run:
            print(ui.yellow(f"🧪 Would create {path}"))
        else:
            os.makedirs(path)
    return roms, bios


def main():
    try:
        return sync()
    except KeyboardInterrupt:
        print(ui.yellow("\n🛑 Interrupted"))
        return 130
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)  # dot_clean inherits this, so a second ^C can't cut it short
        clean.clean_dirs()


def list_devices():
    """Print a table of the devices: name, chip and number of recommended systems."""
    devices = store.load_manifest()["devices"]
    rows = [(d["name"], d["soc"], str(len(d["systems"]))) for d in devices]
    head = ("Device", "Chip", "Systems")
    widths = [max(len(r[i]) for r in rows + [head]) for i in range(3)]
    print(ui.bold(f"{head[0]:<{widths[0]}}  {head[1]:<{widths[1]}}  {head[2]:>{widths[2]}}"))
    for name, soc, count in rows:
        print(f"{name:<{widths[0]}}  {soc:<{widths[1]}}  {count:>{widths[2]}}")
    return 0


def sync():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("base_dir", nargs="?")
    ap.add_argument("-n", "--dry-run", action="store_true")
    ap.add_argument("-e", "--edit", action="store_true")
    ap.add_argument("-a", "--ask", action="store_true")
    ap.add_argument("-u", "--upload-scrapes", action="store_true")
    ap.add_argument("-c", "--clean-scrapes", action="store_true")
    ap.add_argument("--upload", nargs="?", const="")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--diff", nargs="?", const="")
    ap.add_argument("--m3u", nargs="?", const="")
    ap.add_argument("--chd", nargs="?", const="")
    ap.add_argument("--install-tools", action="store_true")
    ap.add_argument("--mirror", nargs="?", const="")
    ap.add_argument("--use-mirror")
    ap.add_argument("--clear-mirror", action="store_true")
    ap.add_argument("--devices", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    args = ap.parse_args()
    if args.help:
        print(help_text())
        return 0
    if args.devices:
        return list_devices()
    local = [m for m, on in (("--m3u", args.m3u is not None), ("--chd", args.chd is not None), ("--install-tools", args.install_tools)) if on]
    if local:
        if len(local) > 1 or args.edit or args.upload is not None or args.diff is not None or args.upload_scrapes or args.clean_scrapes or args.mirror is not None or args.use_mirror or args.clear_mirror:
            raise SystemExit(ui.red(f"❌ {local[0]} can't be combined with other modes"))
        if args.install_tools:
            return external.install_tools_command()
        return chd.chd_command(args) if args.chd is not None else m3u.m3u_command(args)
    if args.replace and args.upload is None:
        raise SystemExit(ui.red("❌ --replace only works together with --upload"))
    usersettings.ensure_bucket()
    mirror_mode = args.mirror is not None or bool(args.use_mirror) or args.clear_mirror
    if args.edit + args.upload_scrapes + args.clean_scrapes + (args.upload is not None) + (args.diff is not None) + mirror_mode > 1:
        raise SystemExit(ui.red("❌ Use only one of --edit, --upload, --diff, --upload-scrapes, --clean-scrapes, --mirror, "
                             "--use-mirror and --clear-mirror"))
    if args.upload is not None:
        return upload.upload_command(args)
    if args.diff is not None:
        return diff.diff_command(args)
    if mirror_mode:
        return mirroring.mirror_command(args)
    if args.edit or args.upload_scrapes or args.clean_scrapes:
        code = edit.edit_manifest() if args.edit else scrape_files.upload_scrapes(args) if args.upload_scrapes else scrape_files.clean_scrapes(args)
        mirror = usersettings.load_settings().get("mirror")
        if mirror and not code and not args.dry_run:  # pick up the games just added
            print()
            mirroring.use_mirror(mirror, False)
        return code
    base = os.path.abspath(os.path.expanduser(args.base_dir or os.getcwd()))

    print(ui.bold(f"🎮 sync-roms") + ui.dim(f"  s3://{runtime.BUCKET}  profile={runtime.PROFILE}"))
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
    if setup:
        device, layout_name = setup
        print(ui.bold(f"💾 Remembered {ui.cyan(card)}: ")
              + f"{device['name'] if device else 'Full'} · {layouts[layout_name]['label']}")
        if not args.ask or ui.confirm("Use this saved setup?"):
            dirs = prepare_dirs(base, layouts[layout_name], args.dry_run, ask=False)
    if dirs is None:
        device, layout_name = picker.choose_setup(manifest)
        dirs = prepare_dirs(base, layouts[layout_name], args.dry_run)
        if dirs is None:
            raise SystemExit(ui.yellow("👋 Cancelled."))
        if not args.dry_run:
            store.save_card(card, device, layout_name)
    layout = layouts[layout_name]
    unzip = layout.get("unzip", False)  # ROMs go in flat and unzipped (Slot)
    roms_dir, bios_dir = dirs
    if not args.dry_run:
        clean._clean_root = base
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

    print("📏 Reading ROM sizes...")
    with ThreadPoolExecutor(runtime.WORKERS) as ex:
        listings = dict(zip((s["bucket"] for s in systems),
                            ex.map(lambda s: s3.list_sizes(s["bucket"] + "/")
                                   if s.get("full_system") or store.listed(s) else {}, systems)))

    def available(s):
        return store.available_keys(s, listings[s["bucket"]])

    def sizes(s):
        """(bytes still to download, total bytes) for a system's ROMs."""
        have, need, total = listings[s["bucket"]], 0, 0
        for k in available(s):
            size = have.get(k, 0)
            total += size
            if downloads.plan_downloads([(k, os.path.join(roms_dir, s["folders"][layout_name], downloads.rom_rel(k, unzip)), size)], unzip):
                need += size
        return need, total

    rows = [(f"{s['name']}  ({len(available(s))} roms)", bool(available(s)), *sizes(s)) for s in systems]
    present = [i for i, s in enumerate(systems)
               if available(s) and (device or downloads.has_local_files(os.path.join(roms_dir, s["folders"][layout_name])))]
    chosen = picker.pick_systems(rows, present)
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
                rom_jobs.append((key, os.path.join(dest, downloads.rom_rel(key, unzip)), have[key]))
            else:
                missing.append(key)
    ui.report_missing(missing, "ROM(s)")
    # systems can share a folder (Onion: WS, NGP), so a folder's expected files are the union over all of them
    for dest in sorted({dest_of(s) for s in chosen if available(s)}):
        extras += downloads.find_extras(dest, [k for t in systems if dest_of(t) == dest for k in available(t)], unzip)

    bios_keys = sorted({"BIOS/" + f for s in chosen for f in s["bios"]["files"]})
    bios_have = s3.list_sizes("BIOS/") if bios_keys else {}
    bios_jobs = [(k, os.path.join(bios_dir, k[len("BIOS/"):]), bios_have[k])
                 for k in bios_keys if k in bios_have]
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

    def scrape_plan(present):
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
        for key, path, _ in rom_todo + bios_todo:
            print(f"  {key} {ui.dim('→')} {path}")
        if unzip:
            pending = {j[1] for j in rom_todo} | set(chd.card_archives({dest_of(s) for s in chosen}))
            print(f"📦 Archives to extract: {len([p for p in pending if p.lower().endswith(external.ARCHIVE_EXTS)])}")
        for path in extras:
            print(f"  {ui.red('would delete')} {path}")
        if scrapes:
            scrape_plan.describe_scrape_plan(scrape_plan(lambda path: True))
            print(f"🧹 Media on the card for ROMs it doesn't have: {len(scrape_plan.stale_media(layout_name, manifest['systems'], roms_dir, es_dir, base))} file(s) to remove")
        if layout_name == "esde":
            clean.clean_android_media(base, card, True, args.ask)
        return 0

    if extras:
        for path in extras[:10]:
            print(ui.dim(f"     {path}"))
        if len(extras) > 10:
            print(ui.dim(f"     … and {len(extras) - 10} more"))
        if ui.confirm(f"🗑️  Delete these {len(extras)} local file(s)?", default=False):
            for path in extras:
                os.remove(path)
            print(ui.green(f"  🧹 Deleted {len(extras)} file(s)"))
        else:
            print(ui.yellow("  ↩️  Keeping them"))

    failed = downloads.run_downloads(rom_todo, "ROMs", "💿", roms_dir) + downloads.run_downloads(bios_todo, "BIOS", "🧠", bios_dir)
    if unzip:
        # also archives already on the card (not just new downloads), e.g. from an interrupted run
        archives = sorted({j[1] for j in rom_todo} | set(chd.card_archives({dest_of(s) for s in chosen})))
        for path, error in chd.unzip_roms(archives):
            failed += 1
            print(ui.red(f"  ❌ {os.path.relpath(path, roms_dir)}: {error}"))
    stale = []
    if scrapes:
        plan = scrape_plan(os.path.exists)
        scrape_plan.describe_scrape_plan(plan)
        failed += scrape_plan.apply_scrape_plan(plan, base)
        stale = scrape_plan.stale_media(layout_name, manifest["systems"], roms_dir, es_dir, base)
    for path in stale:
        try:
            os.remove(path)
        except OSError as e:
            print(ui.red(f"  ❌ {path}: {e}"))
    if stale:
        print(ui.green(f"🧹 Removed {len(stale)} media file(s) for ROMs that aren't on this card"))
    if layout_name == "esde":  # only Android cards have these folders; a Knulli card's "music" must stay
        clean.clean_android_media(base, card, False, args.ask)
    print(ui.green("\n🎉 Done!") if not failed else ui.red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

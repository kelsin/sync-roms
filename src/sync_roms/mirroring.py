"""Local mirror of the bucket."""
import os
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import BotoCoreError, ClientError

from . import downloads, runtime, s3, scrape_plan, store, ui, usersettings


MIRROR_PRUNE_ASK = 25  # delete more unreferenced mirror files than this (or over a tenth of it) only after confirming


def mirror_wanted(manifest):
    """{bucket key: size} of everything the game lists and BIOS requirements reference that is in the bucket: the ROMs a sync
    installs, every system's BIOS files, the scraped data of those ROMs, and all of scrapes/esde/."""
    systems = manifest["systems"]
    todo = [s for s in systems if s.get("full_system") or store.listed(s)]
    with ThreadPoolExecutor(runtime.WORKERS) as ex:
        roms = list(ex.map(lambda s: s3.list_sizes(s["bucket"] + "/"), todo))
        scrapes = list(ex.map(lambda s: s3.list_sizes(f"{scrape_plan.SCRAPES}/{s['bucket']}/"), todo))
    wanted = {}
    for s, have, scraped in zip(todo, roms, scrapes):
        keys = [k for k in store.available_keys(s, have) if k in have]
        wanted.update((k, have[k]) for k in keys)
        stems = {os.path.splitext(k.split("/", 1)[1])[0] for k in keys}
        for key, size in scraped.items():
            parts = key.split("/")
            if key == f"{scrape_plan.SCRAPES}/{s['bucket']}/metadata.json" or (
                    len(parts) > 3 and parts[2] in scrape_plan.BUCKET_MEDIA and os.path.splitext("/".join(parts[3:]))[0] in stems):
                wanted[key] = size
    bios = s3.list_sizes("BIOS/")
    for s in systems:
        for f in s["bios"]["files"]:
            if "BIOS/" + f in bios:
                wanted["BIOS/" + f] = bios["BIOS/" + f]
    wanted.update((k, v) for k, v in s3.list_sizes(f"{scrape_plan.SCRAPES}/esde/").items() if not k.endswith("/"))
    return wanted


def refresh_mirror(root, dry_run=False):
    """Make root hold exactly what the game lists reference: download what's missing or a different size,
    delete the rest. Returns the number of failed downloads."""
    if not os.path.exists(os.path.join(root, runtime.MIRROR_MARKER)):
        if os.path.isdir(root) and os.listdir(root):
            raise SystemExit(ui.red(f"❌ {root} isn't empty and isn't a sync-roms mirror"))
        if not dry_run:
            os.makedirs(root, exist_ok=True)
            open(os.path.join(root, runtime.MIRROR_MARKER), "w").close()
    print("📄 Fetching manifests...")
    manifest = store.load_manifest(store.all_card_names())
    print("📏 Listing the bucket...")
    wanted = mirror_wanted(manifest)
    have = {k: s for k, s in s3.mirror_sizes(root).items() if k != runtime.MIRROR_MARKER}
    jobs = []
    for k, s in wanted.items():
        try:
            jobs.append((k, s3.safe_join(root, k), s))
        except ValueError as e:
            print(ui.yellow(f"  ⚠️  skipping {e}"))
    todo = downloads.plan_downloads(jobs)
    stale = sorted(set(have) - set(wanted))
    print(f"🪞 Mirror: {ui.bold(str(len(todo)))} to download ({ui.human_size(sum(j[2] for j in todo))}), "
          f"{len(wanted) - len(todo)} up to date, {ui.bold(str(len(stale)))} to delete")
    if dry_run:
        for key, _, _ in todo:
            print(f"  {key}")
        for key in stale:
            print(f"  {ui.red('would delete')} {key}")
        return 0
    failed = downloads.run_downloads(todo, "Mirror", "🪞", root)
    if stale and failed:
        print(ui.yellow(f"  ⚠️  Not deleting the {len(stale)} unreferenced file(s): {failed} download(s) failed, so the list may be incomplete"))
        stale = []
    elif stale and (len(stale) > MIRROR_PRUNE_ASK or len(stale) * 10 > len(have)):
        # a lot of the mirror going at once is more likely a listing glitch or a trimmed list than intent
        for key in stale[:10]:
            print(ui.dim(f"     {key}"))
        if len(stale) > 10:
            print(ui.dim(f"     … and {len(stale) - 10} more"))
        if not ui.confirm(f"🗑️  Delete these {len(stale)} file(s) no longer referenced?", default=False):
            print(ui.yellow("  ↩️  Keeping them"))
            stale = []
    for key in stale:
        os.remove(s3.safe_join(root, key))
    for folder, _, _ in os.walk(root, topdown=False):
        if folder != root and not os.listdir(folder):
            os.rmdir(folder)
    if stale:
        print(ui.green(f"  🧹 Deleted {len(stale)} file(s) no longer referenced"))
    return failed


def use_mirror(root, dry_run):
    """Refresh the saved mirror from the bucket, then make this run read from it."""
    if not os.path.exists(os.path.join(root, runtime.MIRROR_MARKER)):
        print(ui.yellow(f"  ⚠️  Mirror {root} not found; using the bucket"))
        return
    print(ui.bold(f"🪞 Local mirror {ui.cyan(root)}"))
    try:
        failed = refresh_mirror(root, dry_run)
        if failed:
            ui.warn(f"{failed} mirror download(s) failed; files missing from the mirror will fail to copy. Re-run to retry")
    except (ClientError, BotoCoreError, OSError, SystemExit) as e:  # S3 failed, or the folder isn't a mirror
        ui.warn(f"Couldn't refresh the mirror ({e}); using what it has")
    if dry_run:
        print(ui.dim("  (dry run: the mirror was not refreshed, so this plan reads what it already has)"))
    runtime._mirror_root = root


def mirror_command(args):
    if args.clear_mirror:
        usersettings.save_setting("mirror", None)
        print(ui.green("🪞 Mirror setting cleared") + ui.dim(" (the mirror's files are left alone)"))
        return 0
    given = args.use_mirror or args.mirror
    root = given or usersettings.load_settings().get("mirror")
    if not root:
        raise SystemExit(ui.red("❌ No mirror folder: give one (--mirror DIR) or save one with --use-mirror DIR"))
    root = os.path.abspath(os.path.expanduser(root))
    print(ui.bold(f"🪞 Mirror {ui.cyan(root)}") + ui.dim(f"  s3://{runtime.BUCKET}  profile={runtime.PROFILE}"))
    failed = refresh_mirror(root, args.dry_run)
    if args.use_mirror and not args.dry_run:
        usersettings.save_setting("mirror", root)
        print(ui.green(f"💾 Saved {root} as the local mirror"))
    print(ui.green("\n🎉 Done!") if not failed else ui.red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0

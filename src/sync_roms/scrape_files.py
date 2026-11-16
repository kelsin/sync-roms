"""Storage's scrapes/ folder: the ROMs it is for, derived art names and cleanup."""
import json
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor


from . import inventory, runtime, s3, scrape_plan, store, ui, vita


def bucket_roms(systems, all_files=False):
    """{storage folder: set of ROM paths in it}, from storage's real contents.

    By default only the ROMs a sync would install (the games the cards list, or every file of a
    full system). With all_files, every file in the system's storage folder.
    """
    todo = systems if all_files else [s for s in systems if s.get("full_system") or store.listed(s)]
    with ThreadPoolExecutor(runtime.WORKERS) as ex:
        listings = list(ex.map(lambda s: inventory.files(s["bucket"] + "/") if all_files else store.list_system(s), todo))
    roms = {s["bucket"]: set() for s in systems}
    for s, have in zip(todo, listings):
        keys = (k for k in have if not k.endswith("/") and not vita.is_extra(k)) if all_files else (k for k in store.available_keys(s, have) if k in have and not vita.is_extra(k))
        roms[s["bucket"]] = {k.split("/", 1)[1] for k in keys}
    return roms


def rom_stems(roms):
    """{system: ROM paths without their extension}, which is how scraped media is named."""
    return {system: {os.path.splitext(r)[0] for r in paths} for system, paths in roms.items()}


def derived_art(system, stem, found):
    """[(key, source path or None, (max width, max height))] of the Onion box art and Slot label a ROM gets.

    found: {media type: local path} of the ROM's art. Onion's Imgs folder is flat, so ROMs in subfolders get
    none; Slot labels are only made for the systems in SLOT_LABEL_MAX.
    """
    wanted = [(scrape_plan.ONION_TYPE, scrape_plan.ONION_ART, scrape_plan.ONION_MAX)] if "/" not in stem else []
    if system in scrape_plan.SLOT_LABEL_MAX:
        wanted.append((scrape_plan.SLOT_TYPE, scrape_plan.SLOT_ART, scrape_plan.SLOT_LABEL_MAX[system]))
    return [(f"{scrape_plan.SCRAPES}/{system}/{kind}/{stem}.png", next((found[t] for t in order if t in found), None), box)
            for kind, order, box in wanted]


def text_keys(existing):
    """Keys under scrapes/ of the metadata.json files we merge into."""
    return [k for k in existing if k.endswith("/metadata.json")]


def plan_clean(existing, roms, remote_texts):
    """What in scrapes/ no longer matches an available ROM.

    Returns (delete keys, rewrites [(key, text)], per-system counts, warnings).
    """
    stems = rom_stems(roms)
    delete, rewrites, warnings = [], [], []
    per = defaultdict(lambda: {"media": 0, "bytes": 0, "entries": 0})
    for key, size in sorted(existing.items()):
        parts = key.split("/")
        if len(parts) < 3 or parts[0] != scrape_plan.SCRAPES or key.endswith("/"):
            continue
        system = parts[1]
        if parts[2] == "metadata.json" and len(parts) == 3:
            try:
                data = json.loads(remote_texts[key])
            except (KeyError, ValueError):
                warnings.append(f"{key} isn't valid JSON, skipped")
                continue
            keep = {k: v for k, v in data.items() if k in roms.get(system, ())}
            if len(keep) == len(data):
                continue
            per[system]["entries"] += len(data) - len(keep)
            if keep:
                rewrites.append((key, scrape_plan.dump_json(keep)))
            else:
                delete.append(key)
        elif parts[2] in scrape_plan.BUCKET_MEDIA and len(parts) > 3:
            if os.path.splitext("/".join(parts[3:]))[0] not in stems.get(system, ()):
                delete.append(key)
                per[system]["media"] += 1
                per[system]["bytes"] += size
    return delete, rewrites, per, warnings


def clean_scrapes(args):
    """Remove scrapes/ media and metadata for ROMs that aren't in storage (any ROM file, listed or not)."""
    print(ui.bold("🧹 Clean scrapes") + ui.dim(f"  {s3.access(True)}"))
    try:
        manifest = store.load_manifest()
        print("📏 Listing every ROM in storage...")
        roms = bucket_roms(manifest["systems"], all_files=True)
        print("☁️  Listing scrapes/...")
        existing = inventory.files(scrape_plan.SCRAPES + "/")
        remote_texts = s3.fetch_texts(text_keys(existing))
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    delete, rewrites, per, warnings = plan_clean(existing, roms, remote_texts)
    for w in warnings:
        print(ui.yellow(f"  ⚠️  {w}"))
    if not delete and not rewrites:
        print(ui.green("Nothing to clean ✨"))
        return 0
    print(ui.bold("\nFor ROMs that aren't in storage:"))
    for system in sorted(per):
        c = per[system]
        print(f"  {system}: {c['media']} media file(s) ({ui.human_size(c['bytes'])}), {c['entries']} metadata entr{'y' if c['entries'] == 1 else 'ies'}")
    for key in delete[:10]:
        print(ui.dim(f"     {key}"))
    if len(delete) > 10:
        print(ui.dim(f"     … and {len(delete) - 10} more"))
    if args.dry_run:
        print(ui.yellow("\n🧪 Dry run — nothing deleted"))
        return 0
    if not ui.confirm(f"🗑️  Permanently delete {len(delete)} object(s) and rewrite {len(rewrites)} metadata file(s)?", default=False):
        print(ui.yellow("↩️  Keeping everything"))
        return 0
    failed = 0
    try:
        for key, text in rewrites:
            s3.put_text(key, text)
        failed = len(s3.delete_keys(delete)) if delete else 0
    except s3.ERRORS as e:
        ui.fail(f"{e}", 3)
    print(ui.green("\n🎉 Done!") if not failed else ui.red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0

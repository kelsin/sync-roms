"""ES-DE style scrape data: gamelists, settings, upload and cleanup."""
import json
import os
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from botocore.exceptions import BotoCoreError, ClientError

from . import runtime, s3, scrape_plan, store, ui, upload


def bucket_roms(systems, all_files=False):
    """{bucket folder: set of ROM paths in it}, from the bucket's real contents.

    By default only the ROMs a sync would install (the games games.json lists, or every file of a
    full system). With all_files, every file in the system's bucket folder.
    """
    todo = systems if all_files else [s for s in systems if s.get("full_system") or store.listed(s)]
    with ThreadPoolExecutor(runtime.WORKERS) as ex:
        listings = list(ex.map(lambda s: s3.list_sizes(s["bucket"] + "/"), todo))
    roms = {s["bucket"]: set() for s in systems}
    for s, have in zip(todo, listings):
        keys = (k for k in have if not k.endswith("/")) if all_files else (k for k in store.available_keys(s, have) if k in have)
        roms[s["bucket"]] = {k.split("/", 1)[1] for k in keys}
    return roms


def rom_stems(roms):
    """{system: ROM paths without their extension}, which is how scraped media is named."""
    return {system: {os.path.splitext(r)[0] for r in paths} for system, paths in roms.items()}


def plan_upload(es_dir, roms, existing, remote_texts):
    """What to upload from an ES-DE data folder.

    roms: {system: available ROM paths}; existing: {key: size} under scrapes/;
    remote_texts: {key: text} of the bucket's text files. Returns a dict with
    files [(key, path, size)], texts [(key, text, label)], present (files already in the bucket),
    derived [(key, source path, source size, (max width, max height))] (Onion box art and Slot labels the
    bucket doesn't have yet, made from the local image even when that image itself was already uploaded),
    derived_present and warnings.
    """
    stems = rom_stems(roms)
    plan = {"files": [], "texts": [], "present": 0, "derived": [], "derived_present": 0, "warnings": []}

    def want_file(key, path):
        size = os.path.getsize(path)
        if existing.get(key) == size:
            plan["present"] += 1
        else:
            plan["files"].append((key, path, size))

    def read(path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    gamelists = os.path.join(es_dir, "gamelists")
    for system in sorted(os.listdir(gamelists)) if os.path.isdir(gamelists) else []:
        path = os.path.join(gamelists, system, "gamelist.xml")
        if not roms.get(system) or not os.path.isfile(path):
            continue
        try:
            local = scrape_plan.parse_gamelist(read(path))
        except (ET.ParseError, OSError, UnicodeDecodeError) as e:
            plan["warnings"].append(f"{system}: couldn't read gamelist.xml ({e}), skipped")
            continue
        local = {k: v for k, v in local.items() if k in roms[system] and v}
        key = f"{scrape_plan.SCRAPES}/{system}/metadata.json"
        old = remote_texts.get(key, "")
        try:
            remote = json.loads(old) if old else {}
        except ValueError:
            plan["warnings"].append(f"{key} in the bucket isn't valid JSON, skipped")
            continue
        merged = scrape_plan.merge_metadata(remote, local)
        if local and scrape_plan.dump_json(merged) != old:
            new = len(set(merged) - set(remote))
            plan["texts"].append((key, scrape_plan.dump_json(merged), f"{system} metadata (+{new} new, {len(local) - new} checked)"))

    media = os.path.join(es_dir, "downloaded_media")
    art = defaultdict(dict)  # (system, ROM name) -> {media type: local path} for Onion box art and Slot labels
    for system in sorted(os.listdir(media)) if os.path.isdir(media) else []:
        if not stems.get(system):
            continue
        for mtype in sorted(scrape_plan.MEDIA_TYPES):
            base = os.path.join(media, system, mtype)
            for rel, full in scrape_plan.walk_files(base) if os.path.isdir(base) else []:
                stem = os.path.splitext(rel)[0]
                if stem in stems[system]:
                    want_file(f"{scrape_plan.SCRAPES}/{system}/{mtype}/{rel}", full)
                    if mtype in scrape_plan.ONION_ART + scrape_plan.SLOT_ART:
                        art[(system, stem)][mtype] = full
    for (system, stem), found in sorted(art.items()):
        wanted = [(scrape_plan.ONION_TYPE, scrape_plan.ONION_ART, scrape_plan.ONION_MAX)] if "/" not in stem else []  # Onion's Imgs folder is flat
        if system in scrape_plan.SLOT_LABEL_MAX:
            wanted.append((scrape_plan.SLOT_TYPE, scrape_plan.SLOT_ART, scrape_plan.SLOT_LABEL_MAX[system]))
        for kind, order, box in wanted:
            key = f"{scrape_plan.SCRAPES}/{system}/{kind}/{stem}.png"
            source = next((found[t] for t in order if t in found), None)
            if key in existing:
                plan["derived_present"] += 1
            elif source:
                plan["derived"].append((key, source, os.path.getsize(source), box))

    themes = os.path.join(es_dir, "themes")
    for rel, full in scrape_plan.walk_files(themes, skip_top=("themes-list",)) if os.path.isdir(themes) else []:
        want_file(f"{scrape_plan.SCRAPES}/esde/themes/{rel}", full)

    collections = os.path.join(es_dir, "collections")
    for name in sorted(os.listdir(collections)) if os.path.isdir(collections) else []:
        if name.endswith(".cfg") and not name.startswith("."):
            key = f"{scrape_plan.SCRAPES}/esde/collections/{name}"
            old = remote_texts.get(key, "")
            new = scrape_plan.merge_lines(old, read(os.path.join(collections, name)))
            if new and new != old:
                plan["texts"].append((key, new, f"collection {name}"))

    settings = os.path.join(es_dir, "settings", "es_settings.xml")
    if os.path.isfile(settings):
        local = scrape_plan.safe_settings(read(settings))
        key = f"{scrape_plan.SCRAPES}/esde/settings.json"
        old = remote_texts.get(key, "")
        try:
            remote = json.loads(old) if old else {}
        except ValueError:
            plan["warnings"].append(f"{key} in the bucket isn't valid JSON, skipped")
            remote = None
        if remote is not None and local and scrape_plan.dump_json({**remote, **local}) != old:
            plan["texts"].append((key, scrape_plan.dump_json({**remote, **local}), f"settings (+{len(set(local) - set(remote))} new)"))
    return plan


def text_keys(existing):
    """Keys under scrapes/ that are text files we merge into."""
    return [k for k in existing if k.endswith("/metadata.json") or "/esde/collections/" in k
            or k == f"{scrape_plan.SCRAPES}/esde/settings.json"]


def upload_scrapes(args):
    """Upload BASE_DIR/ES-DE scraped data to the bucket's scrapes/ folder, merging with what's there."""
    base = os.path.abspath(os.path.expanduser(args.base_dir or os.getcwd()))
    es_dir = os.path.join(base, "ES-DE")
    if not os.path.isdir(es_dir):
        raise SystemExit(ui.red(f"❌ No ES-DE folder in {base}"))
    saved = store.load_cards().get(os.path.basename(base) or base)
    if isinstance(saved, dict) and saved.get("layout") not in (None, "esde"):
        raise SystemExit(ui.red(f"❌ {base} is set up as a {saved['layout']} card; scraped data is only uploaded from the esde layout"))

    print(ui.bold("☁️  Upload scrapes") + ui.dim(f"  read={runtime.PROFILE}  write={runtime.WRITE_PROFILE}  from {es_dir}"))
    try:
        manifest = store.load_manifest([os.path.basename(base) or base])
        print("📏 Listing the ROMs available in the bucket...")
        roms = bucket_roms(manifest["systems"])
        print("☁️  Listing what's already in scrapes/...")
        existing = s3.list_sizes(scrape_plan.SCRAPES + "/")
        remote_texts = s3.fetch_texts(text_keys(existing))
        print("🔎 Comparing...")
        plan = plan_upload(es_dir, roms, existing, remote_texts)
    except (ClientError, BotoCoreError) as e:
        raise SystemExit(ui.red(f"❌ {e}"))
    for w in plan["warnings"]:
        print(ui.yellow(f"  ⚠️  {w}"))
    files, texts, derived = plan["files"], plan["texts"], plan["derived"]
    if derived and not scrape_plan.can_shrink():
        print(ui.yellow(f"  ⚠️  Onion box art and Slot labels need Pillow or macOS sips to resize images; skipping {len(derived)} file(s)"))
        derived = []
    print(f"\n📝 Text files to write: {ui.bold(str(len(texts)))}")
    for _, _, label in texts[:15]:
        print(ui.dim(f"     {label}"))
    if len(texts) > 15:
        print(ui.dim(f"     … and {len(texts) - 15} more"))
    print(f"🖼️  Files to upload (media, themes): {ui.bold(str(len(files)))} "
          f"({ui.human_size(sum(f[2] for f in files))}), {plan['present']} already there")
    print(f"🧅 Onion box art and Slot labels to create from local images: {ui.bold(str(len(derived)))}, {plan['derived_present']} already there")
    if not files and not texts and not derived:
        print(ui.green("Nothing to upload ✨"))
        return 0
    if args.dry_run:
        print(ui.yellow("\n🧪 Dry run — nothing uploaded"))
        for key, _, size, *_ in (files + derived)[:20]:
            print(f"  {key} {ui.dim(ui.human_size(size))}")
        if len(files) + len(derived) > 20:
            print(ui.dim(f"  … and {len(files) + len(derived) - 20} more"))
        return 0
    if not ui.confirm(f"☁️  Upload to s3://{runtime.BUCKET}/{scrape_plan.SCRAPES}/ ?", default=False):
        print(ui.yellow("👋 Cancelled."))
        return 0
    failed = 0
    with ThreadPoolExecutor(runtime.WORKERS) as ex:
        for label, f in [(label, ex.submit(s3.put_text, key, text)) for key, text, label in texts]:
            try:
                f.result()
                print(f"  ✅ {label}")
            except Exception as e:
                failed += 1
                print(f"  ❌ {ui.red(label)}: {(getattr(e, 'stderr', None) or str(e)).strip()}")
    failed += upload.run_uploads(files + derived) if files or derived else 0
    print(ui.green("\n🎉 Done!") if not failed else ui.red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0


def plan_clean(existing, roms, remote_texts):
    """What in scrapes/ no longer matches an available ROM.

    Returns (delete keys, rewrites [(key, text)], per-system counts, warnings). Themes, collections
    and settings (scrapes/esde/) are never touched.
    """
    stems = rom_stems(roms)
    delete, rewrites, warnings = [], [], []
    per = defaultdict(lambda: {"media": 0, "bytes": 0, "entries": 0})
    for key, size in sorted(existing.items()):
        parts = key.split("/")
        if len(parts) < 3 or parts[0] != scrape_plan.SCRAPES or parts[1] == "esde" or key.endswith("/"):
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
    """Remove scrapes/ media and metadata for ROMs that aren't in the bucket (any ROM file, listed in games.json or not)."""
    print(ui.bold("🧹 Clean scrapes") + ui.dim(f"  read={runtime.PROFILE}  write={runtime.WRITE_PROFILE}"))
    try:
        manifest = store.load_manifest()
        print("📏 Listing every ROM in the bucket...")
        roms = bucket_roms(manifest["systems"], all_files=True)
        print("☁️  Listing scrapes/...")
        existing = s3.list_sizes(scrape_plan.SCRAPES + "/")
        remote_texts = s3.fetch_texts([k for k in text_keys(existing) if k.endswith("/metadata.json")])
    except (ClientError, BotoCoreError) as e:
        raise SystemExit(ui.red(f"❌ {e}"))
    delete, rewrites, per, warnings = plan_clean(existing, roms, remote_texts)
    for w in warnings:
        print(ui.yellow(f"  ⚠️  {w}"))
    if not delete and not rewrites:
        print(ui.green("Nothing to clean ✨"))
        return 0
    print(ui.bold("\nFor ROMs that aren't in the bucket:"))
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
    except (ClientError, BotoCoreError) as e:
        raise SystemExit(ui.red(f"❌ {e}"))
    print(ui.green("\n🎉 Done!") if not failed else ui.red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0

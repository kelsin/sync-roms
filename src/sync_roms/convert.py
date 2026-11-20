"""`cards convert`: plan and apply the renames that take a card's files from one layout to another on the same filesystem."""
import os
import shutil

from sync_roms import commands, downloads, frontend, m3u, picker, saves, scrape_plan, store, ui

PLAYLIST_NOTE = "playlist paths differ between layouts; sync rewrites it"


def _listed(path):
    """Directory entries of path, [] when it is no directory."""
    try:
        return os.listdir(path)
    except OSError:
        return []


def _exact_dir(base, *parts):
    """base/parts joined as each part is spelled on disk: exactly so, or (a case-only rename may have stopped partway)
    as its only other-case spelling; else None."""
    path = base
    for part in parts:
        names = _listed(path)
        if part not in names:
            same = [m for m in names if m.lower() == part.lower()]
            if len(same) != 1:
                return None
            part = same[0]
        path = os.path.join(path, part)
    return path if os.path.isdir(path) else None


def _scan(folder, keep_dir=None, skip_db=False):
    """(files, ignored): the relative paths (with /) of the ROM files under folder, and of what the frontends put there
    instead (what downloads.walk_roms leaves out, dot folders included but not dotfiles), which a convert leaves alone.
    keep_dir (the layout's disc folder) is walked although it is a dot folder."""
    files, ignored = [], []
    for root, dirs, names in os.walk(folder):
        rel = os.path.relpath(root, folder)
        at_root = rel == "."
        prefix = "" if at_root else rel.replace(os.sep, "/") + "/"
        keep = []
        for d in sorted(dirs):
            if at_root and d == keep_dir:
                keep.append(d)
            elif d.startswith(".") or (at_root and d.lower() in downloads.IGNORED_ROOT_DIRS):
                ignored.append(prefix + d)
            else:
                keep.append(d)
        dirs[:] = keep
        for f in sorted(names):
            low = f.lower()
            if f.startswith("."):
                continue
            if low in downloads.IGNORED_FILES or (skip_db and low.endswith(".db")) or downloads.TEMP_DOWNLOAD.search(f) \
                    or (at_root and low in downloads.IGNORED_ROOT_FILES):
                ignored.append(prefix + f)
            else:
                files.append(prefix + f)
    return files, ignored


def _flat(files, bucket, layout):
    """{file's path in the layout: its path as the bucket keeps it}: without the layout's disc folder, and without the
    per-game folder of a layout with disc_folders (only a folder m3u.game_folders would make; other folders stay)."""
    disc_dir = layout.get("disc_dir")
    flat = {}
    for rel in files:
        flat[rel] = rel[len(disc_dir) + 1:] if disc_dir and rel.startswith(disc_dir + "/") else rel
    if layout.get("disc_folders"):
        inner = {rel: f"{bucket}/{rel.split('/', 1)[1]}" for rel in files if rel.count("/") == 1}
        by_folder = {}
        for rel, key in inner.items():
            by_folder.setdefault(rel.split("/")[0], {})[key] = rel
        for folder, keys in by_folder.items():
            for key, folder_of in m3u.game_folders(keys).items():
                if folder_of == folder:
                    flat[keys[key]] = key.split("/", 1)[1]
    return flat


def plan_roms(base, systems, old_name, old, new_name, new):
    """([(src, dst)], [(label, reason)]): each system's ROMs moved from its old-layout folder to its new one.
    A system with no folder in the new layout, and a playlist that sync must rewrite, stay where they are."""
    moves, skipped, planned = [], [], set()
    old_root, new_root = old["roms_dir"], new["roms_dir"]
    playlists_differ = bool(old.get("disc_dir")) != bool(new.get("disc_dir"))
    for system in systems:
        old_folder, new_folder = system["folders"].get(old_name), system["folders"].get(new_name)
        if not old_folder or old_folder in planned:
            continue
        src_dir = _exact_dir(base, *old_root.split("/"), *old_folder.split("/"))
        if not src_dir:
            continue
        planned.add(old_folder)
        files, _ = _scan(src_dir, old.get("disc_dir"), old_name in scrape_plan.ONION_LAYOUTS)
        if not files:
            continue
        if not new_folder:
            skipped.append((system["bucket"], f"no folder in the {new_name} layout"))
            continue
        keys = {f"{system['bucket']}/{flat}": rel for rel, flat in _flat(files, system["bucket"], old).items()}
        disc_dir = new.get("disc_dir")
        discs = m3u.disc_keys(keys) if disc_dir else ()
        folders = m3u.game_folders(keys) if new.get("disc_folders") else None
        for key, rel in keys.items():
            if playlists_differ and rel.lower().endswith(".m3u"):
                skipped.append((f"{old_folder}/{rel}", PLAYLIST_NOTE))
                continue
            dst = os.path.join(base, new_root, new_folder, *downloads.rom_rel(key, disc_dir, discs, folders).split("/"))
            src = os.path.join(src_dir, *rel.split("/"))
            if src != dst:
                moves.append((src, dst))
    return moves, skipped


def plan_bios(base, systems, old_name, old, new_name, new):
    """([(src, dst)], [(label, reason)]): each system's BIOS files moved to the first of the new layout's BIOS folders;
    the other tag folders are left for sync to fill."""
    moves, skipped, seen = [], [], set()
    for system in systems:
        if not system["folders"].get(new_name) and new.get("bios_by_tag"):
            continue
        old_dirs = downloads.bios_folders(system, old_name, old, old["bios_dir"]) if system["folders"].get(old_name) \
            or not old.get("bios_by_tag") else []
        new_dirs = downloads.bios_folders(system, new_name, new, new["bios_dir"])
        if not new_dirs:
            continue
        for name in system["bios"]["files"]:
            if name.startswith(".") or name in seen:
                continue
            parts = name.split("/")
            folders = [_exact_dir(base, *d.replace(os.sep, "/").split("/")) for d in old_dirs]
            have = [os.path.join(f, *parts) for f in folders if f and os.path.lexists(os.path.join(f, *parts))]
            if not have:
                continue
            seen.add(name)
            dst = os.path.join(base, new_dirs[0], *parts)
            if have[0] != dst:
                moves.append((have[0], dst))
            skipped += [(name, "extra tag folder; sync will add it") for _ in new_dirs[1:]]
            skipped += [(name, f"another copy in {os.path.dirname(p)}; left in place") for p in have[1:]]
    return moves, skipped


def _new_rom_names(base, system, new_name, new, rom_moves):
    """File names the system's ROM folder in the new layout has once rom_moves are applied."""
    names = set(saves.rom_names(base, new_name, new, system))
    folder = system["folders"].get(new_name)
    if folder:
        root = os.path.join(base, *new["roms_dir"].split("/"), folder) + os.sep
        for _, dst in rom_moves:
            rel = dst[len(root):].split(os.sep) if dst.startswith(root) else []
            if rel and not any(part.startswith(".") for part in rel):
                names.add(rel[-1])
    return names


def plan_saves(base, systems, old_name, old, new_name, new, rom_moves=()):
    """([(src, dst)], [(label, reason)]): the card's RetroArch saves and states moved to the new layout's folders
    (a MinUI save renamed to or from its ROM's file name). Plan it before the ROM moves are applied, passing them as
    rom_moves: the old layout's ROMs say which games are on the card, and the moves give the new layout's ROM file
    names. Files whose game has no ROM on the card are left alone; so are those the new layout can't place (no core,
    no folder) or can't name (several ROMs share the name), which are reported."""
    games, _ = saves.scan(base, old_name, old, systems)
    stems = saves.rom_stems(base, old_name, old, systems)
    by_bucket = {s["bucket"]: s for s in systems}
    minui = new.get("save_naming") == "minui"
    moves, skipped = [], []
    for (bucket, stem), entries in sorted(games.items()):
        if bucket not in (stems.get(stem) or stems.get(saves.retroarch_name(stem)[:-4], set())):
            continue
        system = by_bucket[bucket]
        roms = None
        for e in entries:
            kind, name = ("save" if e["kind"] == "save" else "state"), e["name"]
            label = f"{bucket}/{name}"
            try:
                folder = saves.target_dir(base, new_name, new, system, kind, e["core"])
            except ValueError as err:
                skipped.append((label, str(err)))
                continue
            if minui and kind == "save" and bucket != "psx" and name.endswith(".srm"):
                roms = _new_rom_names(base, system, new_name, new, rom_moves) if roms is None else roms
                if not (renamed := saves.minui_name(name, roms)):
                    if any(os.path.splitext(r)[0] == name[:-4] for r in roms):
                        skipped.append((label, "several ROMs share its name in the new layout"))
                    continue
                name = renamed
            dst = os.path.join(folder, name)
            if e["path"] != dst:
                moves.append((e["path"], dst))
    return moves, skipped


def _prune(folder, base=None):
    """Remove folder and its parents while they are empty, never base or anything outside it."""
    while True:
        if base is not None and (folder == base or not folder.startswith(base + os.sep)):
            return
        try:
            os.rmdir(folder)
        except OSError:
            return
        folder = os.path.dirname(folder)


def _respell(src, dst):
    """src with the folders that only differ from dst's in case renamed to dst's spelling (a case-insensitive
    filesystem answers to either, so renaming the file would leave the folder as it was); returns src as now spelled."""
    s, d = src.split(os.sep), dst.split(os.sep)
    i = 0
    while i < len(s) - 1 and s[i] == d[i]:
        i += 1
    while i < len(s) - 1 and i < len(d) - 1 and s[i] != d[i] and s[i].lower() == d[i].lower():
        old = os.sep.join(s[:i + 1])
        new = os.sep.join(s[:i] + [d[i]])
        try:
            if not os.path.isdir(old) or not os.path.samefile(old, new) or d[i] in _listed(os.sep.join(s[:i]) or os.sep):
                break
        except OSError:
            break
        os.rename(old, old + ".convert-tmp")
        os.rename(old + ".convert-tmp", new)
        s[i] = d[i]
        i += 1
    return os.sep.join(s)


def apply_moves(moves, base=None):
    """Rename each (src, dst), making dst's folders; (done, conflicts, failures): a dst that is already another file is
    left alone with its src, a src that is gone is skipped, and a move the filesystem refuses is a (src, dst, error)
    failure while the rest go on. A case-only rename goes through a temporary name. Folders emptied by the moves are
    removed (never base)."""
    done, conflicts, failures = [], [], []
    for src, dst in moves:
        if not os.path.lexists(src):
            continue
        try:
            real = _respell(src, dst)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.lexists(dst):
                if not os.path.samefile(real, dst):
                    conflicts.append((src, dst))
                    continue
                if real != dst:
                    os.rename(real, real + ".convert-tmp")
                    os.rename(real + ".convert-tmp", dst)
            else:
                os.rename(src, dst)
        except OSError as err:
            failures.append((src, dst, err))
            continue
        done.append((src, dst))
    for src, _ in done:
        _prune(os.path.dirname(src), base)
    return done, conflicts, failures


def _summary(title, moves, skipped, root=None):
    """Print one plan: its moves counted per top folder under root (or each move, with no root), then what is skipped."""
    if not (moves or skipped):
        return
    print(ui.bold(title))
    if root:
        counts = {}
        for src, _ in moves:
            folder = os.path.relpath(src, root).split(os.sep)[0]
            counts[folder] = counts.get(folder, 0) + 1
        for folder, n in sorted(counts.items()):
            print(f"  {folder}: {n} to move")
    else:
        for src, dst in moves:
            print(f"  {src} {ui.dim('→')} {dst}")
    for label, reason in skipped:
        print(f"  {ui.yellow('skipped')} {label} {ui.dim('(' + reason + ')')}")


def _leftovers(base, systems, old_name, old):
    """Frontend files and folders (gamelists, media, dot folders) left in the old layout's ROM folders; a convert
    leaves them untouched."""
    found = []
    for system in systems:
        folder = system["folders"].get(old_name)
        path = _exact_dir(base, *old["roms_dir"].split("/"), *folder.split("/")) if folder else None
        if path:
            _, ignored = _scan(path, old.get("disc_dir"), old_name in scrape_plan.ONION_LAYOUTS)
            found += [os.path.relpath(os.path.join(path, *i.split("/")), base) for i in ignored]
    return list(dict.fromkeys(found))


ROM_FOLDER_MEDIA_DIRS = {"knulli": ("images", "videos", "manuals"), "nextui": (".media",),
                         **{name: ("imgs",) for name in scrape_plan.ONION_LAYOUTS}}


def _media_names(layout_name):
    """Lower-case names a layout's scrapes take inside a system's ROM folder: its gamelist and its media folders."""
    names = set(ROM_FOLDER_MEDIA_DIRS.get(layout_name, ()))
    if scrape_plan.GAMELIST_FILES.get(layout_name) and layout_name not in frontend.ESDE_LAYOUTS:
        names.add(scrape_plan.GAMELIST_FILES[layout_name].lower())
    return names


def plan_media(base, systems, old_name, old, new_name, new):
    """[path]: the old layout's scraped media in its ROM folders (gamelist and media folders), which the new layout
    doesn't use, so nothing reads them after the convert; sync scrapes the new layout's own. A name the new layout also
    uses in the same folder stays."""
    found, seen = [], set()
    old_names = _media_names(old_name)
    same = _media_names(new_name)
    for system in systems:
        old_folder, new_folder = system["folders"].get(old_name), system["folders"].get(new_name)
        if not old_folder or old_folder in seen:
            continue
        seen.add(old_folder)
        folder = _exact_dir(base, *old["roms_dir"].split("/"), *old_folder.split("/"))
        if not folder:
            continue
        shared = same if old["roms_dir"].lower() == new["roms_dir"].lower() and old_folder.lower() == (new_folder or "").lower() else set()
        found += [os.path.join(folder, n) for n in sorted(_listed(folder)) if n.lower() in old_names - shared]
    return found


def remove_media(paths, base=None):
    """Delete each file or folder in paths and the ROM folders that are then empty (never base); the (path, error)
    pairs that could not be removed."""
    failures = []
    for path in paths:
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            elif os.path.lexists(path):
                os.remove(path)
        except OSError as err:
            failures.append((path, err))
    for path in paths:
        _prune(os.path.dirname(path), base)
    return failures


def convert_command(args):
    """`cards convert [CARD] --layout ID [--dry-run] [--yes]`: move the card's ROMs, BIOS and RetroArch saves and
    states to the folders of another layout, then save that layout for the card."""
    base = os.path.abspath(args.card or os.getcwd())
    name = os.path.basename(base)
    cards = store.load_cards()
    if name not in cards:
        ui.fail(f"No card named {name!r}. Set it up with `sync-roms cards new {name} --device ID|full --layout NAME`", 2)
    catalog = store.load_catalog()
    current = picker.saved_setup(cards[name], catalog["devices"], catalog["layouts"], name)
    if not current:
        ui.fail(f"{name!r} has no usable layout. Set it with `sync-roms cards set {name} --layout NAME`", 2)
    if not os.path.isdir(base):
        ui.fail(f"No folder {base}", 2)
    _, new_name = commands.setup_from_flags(catalog, current, None, args.layout)
    old_name = current[1]
    old, new, systems = catalog["layouts"][old_name], catalog["layouts"][new_name], catalog["systems"]
    rom_moves, rom_skipped = plan_roms(base, systems, old_name, old, new_name, new)
    bios_moves, bios_skipped = plan_bios(base, systems, old_name, old, new_name, new)
    save_moves, save_skipped = plan_saves(base, systems, old_name, old, new_name, new, rom_moves)
    planned = rom_moves + bios_moves + save_moves
    media = plan_media(base, systems, old_name, old, new_name, new)
    print(ui.bold(f"{name}: {old_name} → {new_name}"))
    _summary("ROMs", rom_moves, rom_skipped, os.path.join(base, old["roms_dir"]))
    _summary("BIOS", bios_moves, bios_skipped)
    _summary("Saves and states", save_moves, save_skipped)
    if media:
        print(ui.bold(f"Old {old_name} media (deleted)"))
        by_folder = {}
        for path in media:
            by_folder.setdefault(os.path.relpath(os.path.dirname(path), base), []).append(os.path.basename(path))
        for folder, names in by_folder.items():
            print(f"  {folder}: {', '.join(names)}")
    left = [x for x in _leftovers(base, systems, old_name, old) if os.path.join(base, x) not in media]
    if left:
        print(ui.dim("Left in place (frontend files and folders): " + ", ".join(left)))
    if not planned and not media:
        print(ui.green("Nothing to move"))
    if args.dry_run:
        print(ui.yellow("🧪 Dry run: nothing moved, layout not changed"))
        return 0
    if planned or media:
        if not args.yes:
            if not ui.has_terminal():
                ui.fail("Pass --yes to convert without a terminal to confirm on", 2)
            if not ui.confirm(f"Move {len(planned)} files" + (f" and delete the old media in {len(by_folder)} folders?" if media else "?")):
                return 1
        failures = []
        for moves in (save_moves, bios_moves, rom_moves):
            _, conflicts, failed = apply_moves(moves, base)
            failures += failed
            for src, dst in conflicts:
                ui.warn(f"{dst} already exists; left {src} in place")
        if failures:
            for src, dst, err in failures:
                ui.warn(f"could not move {src} → {dst}: {err}")
            ui.fail(f"{len(failures)} move(s) failed; the layout is still {old_name}. Fix the cause and run convert again", 3)
        for path, err in remove_media(media, base):
            ui.warn(f"could not delete {path}: {err}")
    if not store.update_card(name, layout=new_name):
        return 3
    print(ui.green(f"💾 {name} is now {new_name}") + (ui.dim("  (run a sync to fill in the rest)") if planned else ""))
    return 0


def clean_command(args):
    """`cards clean [CARD] [--dry-run] [--yes]`: delete the scraped media other layouts left in the card's ROM
    folders (a convert before this existed, or a card used with another firmware); the card's own layout's stays."""
    base = os.path.abspath(args.card or os.getcwd())
    name = os.path.basename(base)
    cards = store.load_cards()
    if name not in cards:
        ui.fail(f"No card named {name!r}. Set it up with `sync-roms cards new {name} --device ID|full --layout NAME`", 2)
    catalog = store.load_catalog()
    current = picker.saved_setup(cards[name], catalog["devices"], catalog["layouts"], name)
    if not current:
        ui.fail(f"{name!r} has no usable layout. Set it with `sync-roms cards set {name} --layout NAME`", 2)
    if not os.path.isdir(base):
        ui.fail(f"No folder {base}", 2)
    keep_name = current[1]
    layouts, systems = catalog["layouts"], catalog["systems"]
    media = list(dict.fromkeys(
        path for other, layout in layouts.items() if other != keep_name
        for path in plan_media(base, systems, other, layout, keep_name, layouts[keep_name])))
    if not media:
        print(ui.green(f"{name}: no media from other layouts"))
        return 0
    print(ui.bold(f"{name} ({keep_name}): media from other layouts (deleted)"))
    by_folder = {}
    for path in media:
        by_folder.setdefault(os.path.relpath(os.path.dirname(path), base), []).append(os.path.basename(path))
    for folder, names in by_folder.items():
        print(f"  {folder}: {', '.join(names)}")
    if args.dry_run:
        print(ui.yellow("🧪 Dry run: nothing deleted"))
        return 0
    if not args.yes:
        if not ui.has_terminal():
            ui.fail("Pass --yes to delete without a terminal to confirm on", 2)
        if not ui.confirm(f"Delete the media in {len(by_folder)} folders?"):
            return 1
    failures = remove_media(media, base)
    for path, err in failures:
        ui.warn(f"could not delete {path}: {err}")
    print(ui.green(f"🧹 deleted media in {len(by_folder)} folders") if not failures else ui.red(f"{len(failures)} failed"))
    return 3 if failures else 0

"""`cards convert`: plan and apply the renames that take a card's files from one layout to another on the same filesystem."""
import os

from sync_roms import downloads, m3u

PLAYLIST_NOTE = "playlist paths differ between layouts; sync rewrites it"


def _listed(path):
    """Directory entries of path, [] when it is no directory."""
    try:
        return os.listdir(path)
    except OSError:
        return []


def _exact_dir(base, *parts):
    """base/parts joined when each part is spelled exactly so on disk (a case-insensitive filesystem would also
    answer to another spelling); else None."""
    path = base
    for part in parts:
        if part not in _listed(path):
            return None
        path = os.path.join(path, part)
    return path if os.path.isdir(path) else None


def _walk(folder, keep_dir=None):
    """Relative paths (with /) of the files under folder, leaving out dotfiles and dot folders except keep_dir."""
    out = []
    for root, dirs, files in os.walk(folder):
        rel = os.path.relpath(root, folder)
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") or (rel == "." and d == keep_dir))
        out += [(f if rel == "." else rel.replace(os.sep, "/") + "/" + f) for f in sorted(files) if not f.startswith(".")]
    return out


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
        src_dir = _exact_dir(base, old_root, old_folder)
        if not src_dir:
            continue
        planned.add(old_folder)
        files = _walk(src_dir, old.get("disc_dir"))
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
            folders = [_exact_dir(base, *d.split(os.sep)) for d in old_dirs]
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


def _prune(folder):
    """Remove folder and its parents while they are empty."""
    while True:
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


def apply_moves(moves):
    """Rename each (src, dst), making dst's folders; (done, conflicts): a dst that is already another file is left
    alone with its src, and a src that is gone is skipped. A case-only rename goes through a temporary name. Folders emptied by the moves are removed."""
    done, conflicts = [], []
    for src, dst in moves:
        if not os.path.lexists(src):
            continue
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
        done.append((src, dst))
    for src, _ in done:
        _prune(os.path.dirname(src))
    return done, conflicts

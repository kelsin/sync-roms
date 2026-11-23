"""PyUI themes for spruce cards: the .7z assets of spruceUI/PyUI-Themes' release, kept unpacked in storage."""
import glob
import http.client
import json
import os
import shutil
import subprocess
import tempfile

from . import cardfs, downloads, external, github, inventory, picker, previews, runtime, s3, spruce_fixes, spruce_settings, store, ui, usersettings

REPO = "spruceUI/PyUI-Themes"
TAG = "1"
MEMBER_ROOT = ("mnt", "SDCARD", "Themes")  # where each archive keeps its one theme folder


def _junk(name):
    return name == ".DS_Store" or name.startswith("._")


def _release():
    """The release's .7z assets: name, size, updated_at and browser_download_url."""
    data = github.json(f"https://api.github.com/repos/{REPO}/releases/tags/{TAG}")
    return [a for a in data["assets"] if a["name"].lower().endswith(".7z")]


def _download(url, path):
    with github.get(url) as r, open(path, "wb") as f:
        shutil.copyfileobj(r, f)


def _unpack(archive, out):
    """Extract archive into out. Returns the one theme folder name when every extracted file is under
    mnt/SDCARD/Themes/<folder>/, else None."""
    tool = external.find_tool("7z")
    subprocess.run([tool, "x", "-y", "-bso0", "-bsp0", f"-o{out}", "--", archive], check=True)
    folders = set()
    for dirpath, _, names in os.walk(out):
        for name in names:
            if _junk(name):
                continue
            parts = os.path.relpath(os.path.join(dirpath, name), out).split(os.sep)
            if len(parts) < len(MEMBER_ROOT) + 2 or tuple(parts[:len(MEMBER_ROOT)]) != MEMBER_ROOT:
                return None
            folders.add(parts[len(MEMBER_ROOT)])
    return folders.pop() if len(folders) == 1 else None


def _read_state():
    try:
        state = json.loads(s3.get_text(runtime.SPRUCE_THEMES_STATE))
        return {k: v for k, v in state.items() if isinstance(v, dict) and isinstance(v.get("folder"), str)}
    except s3.ERRORS as e:
        if s3.missing(e):
            return {}
        raise


def _files(folder):
    """The files of an unpacked theme folder: {storage-relative path: local path}."""
    return {os.path.relpath(os.path.join(dp, n), folder).replace(os.sep, "/"): os.path.join(dp, n)
            for dp, _, names in os.walk(folder) for n in names if not _junk(n) and not os.path.islink(os.path.join(dp, n))}


def update_storage(dry_run=False):
    """Make storage's PyUI themes match the latest release. Returns an exit code."""
    prefix = runtime.SPRUCE_THEMES_PREFIX
    try:
        s3.check_root()
        state = _read_state()
        assets = _release()
    except FileNotFoundError as e:
        ui.warn(f"The storage folder isn't there (is it mounted?): {e}")
        return 1
    except (OSError, http.client.HTTPException, KeyError, ValueError, *s3.ERRORS) as e:
        ui.warn(f"Couldn't read the PyUI themes release from GitHub or storage: {e}")
        return 1
    released = {a["name"]: a for a in assets}
    todo = [a for a in assets if (state.get(a["name"], {}).get("updated_at"), state.get(a["name"], {}).get("size"))
            != (a["updated_at"], a["size"])]
    gone = [n for n in state if n not in released]
    if not todo and not gone:
        print(ui.green(f"✅ The PyUI themes in storage are already the latest ({len(state)})"))
        return 0
    for a in todo:
        print(f"🎨 PyUI theme {a['name']}: {'update' if a['name'] in state else 'add'}")
    for n in gone:
        print(f"🎨 PyUI theme {n}: remove")
    if dry_run:
        print(ui.dim(f"🧪 Dry run: would change {len(todo) + len(gone)} theme(s) in {prefix}"))
        return 0
    if todo and not external.find_tool("7z"):
        ui.warn("7z isn't installed, so the PyUI themes can't be unpacked; run `sync-roms tools install`")
        return 1
    failed = done = 0
    try:
        listing = inventory.files(prefix, sizes=False)
        for name in gone:
            doomed = [k for k in listing if k.startswith(f"{prefix}{state[name]['folder']}/")]
            s3.delete_keys(doomed)
            listing = {k: v for k, v in listing.items() if k not in set(doomed)}
            del state[name]
        for a in todo:
            try:
                state_entry = _refresh(a, state, prefix, listing)
            except (OSError, http.client.HTTPException, subprocess.CalledProcessError, ValueError, *s3.ERRORS) as e:
                ui.warn(f"{a['name']}: {e}")
                failed = 1
                continue
            if state_entry is None:
                ui.warn(f"{a['name']}: not a single theme folder under mnt/SDCARD/Themes/; skipped")
                failed = 1
            else:
                state[a["name"]] = state_entry
                done += 1
        s3.put_text(runtime.SPRUCE_THEMES_STATE, json.dumps(state, indent=2, sort_keys=True) + "\n")
    except s3.ERRORS as e:
        ui.warn(f"Couldn't update the PyUI themes in {s3.location()}: {e}")
        return 1
    print(ui.green(f"✅ PyUI themes in {s3.location()}: {done} added or updated, {len(gone)} removed"))
    return failed


def _refresh(asset, state, prefix, listing):
    """Download, unpack and upload one asset, replacing its folder. Returns its themes.json entry, or None when the
    archive isn't one theme folder. Raises ValueError when the folder is one sync-roms doesn't own for this asset."""
    old = state.get(asset["name"])
    with tempfile.TemporaryDirectory() as tmp:
        archive, out = os.path.join(tmp, "theme.7z"), os.path.join(tmp, "out")
        _download(asset["browser_download_url"], archive)
        folder = _unpack(archive, out)
        if folder is None:
            return None
        mine = bool(old) and old["folder"] == folder
        if not mine and (any(v["folder"] == folder for v in state.values())
                         or any(k.startswith(f"{prefix}{folder}/") for k in listing)):
            raise ValueError(f"storage already has a folder {folder!r} that isn't this theme's; left alone")
        files = _files(os.path.join(out, *MEMBER_ROOT, folder))
        keep = {f"{prefix}{folder}/{rel}" for rel in files}
        for rel, path in files.items():
            s3.put_file(f"{prefix}{folder}/{rel}", path)
    stale = [k for k in listing
             if (k.startswith(f"{prefix}{folder}/") and k not in keep)
             or (old and old["folder"] != folder and k.startswith(f"{prefix}{old['folder']}/"))]
    s3.delete_keys(stale)
    return {"updated_at": asset["updated_at"], "size": asset["size"], "folder": folder}


def available():
    """The theme folder names in storage (those holding a config.json), sorted ignoring case."""
    prefix = runtime.SPRUCE_THEMES_PREFIX
    names = {k[len(prefix):].split("/")[0] for k in inventory.files(prefix, sizes=False) if k.endswith("/config.json")
             and k.count("/", len(prefix)) == 1}
    return sorted(names, key=lambda n: (n.lower(), n))


def preview(name):
    """Local path of the theme's preview.png (downloaded once), or None when storage has none."""
    key = f"{runtime.SPRUCE_THEMES_PREFIX}{name}/preview.png"
    try:
        return previews._download(key)
    except (OSError, *s3.ERRORS):
        return None


def default_list():
    """The themes every spruce card gets, from settings."""
    names = usersettings.load_settings().get("spruce_themes")
    return [n for n in names if isinstance(n, str)] if isinstance(names, list) else []


def pick(title, chosen, locked=None):
    """Multi pick of themes: the ones in storage, then chosen names storage lacks (dim). The locked theme is always on.
    Returns the names on, or None on Esc."""
    names = available()
    missing = [n for n in chosen if n not in names]
    rows = names + missing
    on = [n in chosen or n == locked for n in rows]
    extras = [[("", "dim")] for _ in names] + [[("not in storage", "dim")] for _ in missing]
    states = picker.filter_list(title, rows, multi=True, initial=on, extras=extras,
                                locked=[n == locked for n in rows], locked_note="this card's current theme",
                                preview=lambda i: preview(rows[i]) if i < len(names) else None)
    if states is None:
        return None
    return [n for n, s in zip(rows, states) if s]


def pick_one(title, current):
    """Pick one theme (or none). Returns the name, None for no theme, False on Esc."""
    names = available()
    labels = ["None (no current theme)"] + names
    i = picker.filter_list(title, labels, cursor=names.index(current) + 1 if current in names else 0,
                           preview=lambda i: preview(names[i - 1]) if i > 0 else None)
    if i is None:
        return False
    return names[i - 1] if i else None


def wanted(card, names):
    """names plus the card's current theme, limited to the themes in storage. Prints a dim note for each one storage
    lacks, and a warning when that is the current theme."""
    current = store.saved_card(card).get("spruce_theme")
    have = available()
    result = []
    for n in [*names, *([current] if isinstance(current, str) and current else [])]:
        if n in have:
            if n not in result:
                result.append(n)
        elif n == current:
            ui.warn(f"The current theme {n} isn't in storage; run sync-roms themes update")
        else:
            print(ui.dim(f"   ⏭️  Spruce theme {n} isn't in storage; skipped"))
    return result


def _plain(name):
    """Whether name is a plain folder name, so Themes/<name>/ is a folder inside Themes/ (a tampered cards.json can't
    point a removal at Themes/ itself or outside it)."""
    return isinstance(name, str) and name not in ("", ".", "..") and os.path.basename(name) == name


def plan(card, base, names, keep):
    """What a card's themes need: jobs ([(key, path, size)] for every file of each wanted theme), remove (installed
    folders to delete) and installed (the card's new spruce_themes_installed). Only folders sync put on the card are
    removed, and never one that is wanted, the card's current theme, or in use by a device (Saves/*-system.json)."""
    saved = store.saved_card(card)
    previous = [n for n in saved.get("spruce_themes_installed") or [] if _plain(n)]
    current = saved.get("spruce_theme")
    have = available()
    use = wanted(card, names)
    prefix = runtime.SPRUCE_THEMES_PREFIX
    jobs = []
    for name in use:
        folder = os.path.join(base, "Themes", name)
        for key, size in sorted(inventory.files(f"{prefix}{name}/").items()):
            downloads.add_job(jobs, key, folder, key[len(prefix) + len(name) + 1:], size)
    installed = previous + [n for n in use if n not in previous and not os.path.isdir(os.path.join(base, "Themes", n))]
    remove = []
    if not keep and have:
        busy = selected(base)
        remove = [n for n in previous if n not in use and n not in busy and n != current]
    return {"jobs": jobs, "remove": remove, "installed": [n for n in installed if n not in remove]}


def todo(jobs):
    """The jobs whose card file is out of date. A file a spruce fix already made right is left alone; a config*.json
    is compared by content, since a changed setting can keep the same size."""
    result = []
    for key, path, size in jobs:
        if spruce_fixes.keeps(path):
            continue
        if os.path.basename(path).lower().startswith("config") and path.lower().endswith(".json"):
            try:
                if cardfs.read(path) == s3.get_text(key).encode("utf-8"):
                    continue
            except (OSError, *s3.ERRORS):
                pass
            result.append((key, path, size))
        elif not downloads.is_current(path, size):
            result.append((key, path, size))
    return result


def remove(base, names, dry_run):
    """Delete the card's Themes/<name>/ folders. Returns the number that failed."""
    failed = 0
    for name in filter(_plain, names):
        path = os.path.join(base, "Themes", name)
        if dry_run:
            print(ui.dim(f"🧪 Dry run: would remove the Spruce theme {name}"))
            continue
        try:
            shutil.rmtree(path)
            print(f"🗑️  Removed the Spruce theme {name}")
        except FileNotFoundError:
            pass
        except OSError as e:
            ui.warn(f"Couldn't remove the Spruce theme {name}: {e}")
            failed += 1
    return failed


def freed(base, names):
    """The bytes removing the card's Themes/<name>/ folders frees."""
    return sum(os.path.getsize(os.path.join(dp, n)) for name in filter(_plain, names)
               for dp, _, files in os.walk(os.path.join(base, "Themes", name)) for n in files
               if not os.path.islink(os.path.join(dp, n)))


def _system_files(base):
    return sorted(glob.glob(os.path.join(glob.escape(base), "Saves", "*-system.json")))


def selected(base):
    """The themes the card's devices have selected: the "theme" of each Saves/*-system.json that parses."""
    names = set()
    for path in _system_files(base):
        try:
            theme = json.loads(cardfs.text(path)).get("theme")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(theme, str) and theme:
            names.add(theme)
    return names


def select(card, base, dry_run):
    """Set "theme" to the card's spruce_theme in every Saves/*-system.json, keeping the rest of each file. Returns the
    failure count (always 0: a file that can't be used is warned about and skipped)."""
    name = store.saved_card(card).get("spruce_theme")
    if not isinstance(name, str) or not name:
        return 0
    files = _system_files(base)
    if not files:
        ui.warn("Saves/*-system.json is missing; the Spruce theme isn't selected (start the card in the device once first)")
        return 0
    changed = 0
    for path in files:
        old = cardfs.text(path)
        try:
            data = json.loads(old)
        except ValueError:
            data = None
        if not isinstance(data, dict):
            ui.warn(f"{os.path.relpath(path, base)} can't be read as Spruce settings; theme not selected there")
            continue
        if data.get("theme") == name:
            continue
        data["theme"] = name
        if not dry_run:
            cardfs.write_text(path, json.dumps(data, indent=spruce_settings._indent(old), ensure_ascii=False)
                              + ("\n" if old.endswith("\n") else ""))
        changed += 1
    if changed:
        print(ui.dim(f"🧪 Dry run: would select the Spruce theme {name} ({changed} file(s))") if dry_run
              else f"🎨 Spruce theme → {name} ({changed} file(s))")
    return 0

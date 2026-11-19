"""RetroArch saves and states on a card: reading them, stashing them in the data folder, planning their copy."""
import datetime
import filecmp
import json
import os
import re
import shutil

from . import store

STATE = re.compile(r"^(?P<stem>.+)\.state(\d+|\.auto)?$")
STASH_KEYS = ("system", "game", "card", "layout", "core", "stashed", "files")


def classify(name):
    """(stem, kind) of a RetroArch file name (save, state or thumbnail), or None for anything else."""
    if name.endswith(".srm") and len(name) > 4:
        return name[:-4], "save"
    m = STATE.match(name)
    if m:
        return m.group("stem"), "state"
    if name.endswith(".png"):
        m = STATE.match(name[:-4])
        if m:
            return m.group("stem"), "thumbnail"
    return None


def _base(base, layout, retroarch_dir):
    return retroarch_dir or os.path.join(base, *layout["retroarch"]["dir"].split("/"))


def rom_stems(base, layout_name, layout, systems):
    """{stem: {system ids}} of every file in the card's ROM folders."""
    stems = {}
    for s in systems:
        folder = s["folders"].get(layout_name)
        if not folder:
            continue
        root = os.path.join(base, *layout["roms_dir"].split("/"), folder)
        for dirpath, _, files in os.walk(root, followlinks=True):
            for f in files:
                stems.setdefault(os.path.splitext(f)[0], set()).add(s["bucket"])
    return stems


def _folders(root, template, systems, layout_name):
    """[(folder, system id or None, core or None)] of a layout's saves or states path template."""
    if "{core}" in template:
        parent = os.path.join(root, *template.split("{core}")[0].split("/"))
        if not os.path.isdir(parent):
            return []
        return [(os.path.join(parent, c), None, c) for c in sorted(os.listdir(parent))
                if os.path.isdir(os.path.join(parent, c))]
    if "{system}" in template:
        return [(os.path.join(root, *template.format(system=s["folders"][layout_name]).split("/")),
                 s["bucket"], None) for s in systems if s["folders"].get(layout_name)]
    return [(os.path.join(root, *template.split("/")), None, None)]


def scan(base, layout_name, layout, systems, retroarch_dir=None):
    """({(system, stem): [entry]}, skipped): the card's RetroArch files by game. skipped counts files whose game
    isn't on the card."""
    root = _base(base, layout, retroarch_dir)
    ra = layout["retroarch"]
    stems = rom_stems(base, layout_name, layout, systems)
    games, skipped, seen = {}, 0, set()
    for template in (ra["saves"], ra["states"]):
        for folder, system, core in _folders(root, template, systems, layout_name):
            if folder in seen or not os.path.isdir(folder):
                continue
            seen.add(folder)
            for name in sorted(os.listdir(folder)):
                path = os.path.join(folder, name)
                c = classify(name)
                if not c or not os.path.isfile(path):
                    continue
                stem, kind = c
                found = {system} if system else stems.get(stem, set())
                if len(found) != 1:
                    skipped += 1
                    continue
                st = os.stat(path)
                games.setdefault((next(iter(found)), stem), []).append(
                    {"path": path, "name": name, "kind": kind, "core": core, "size": st.st_size,
                     "mtime": st.st_mtime})
    return games, skipped


def stash_root():
    """Folder holding every stash."""
    return os.path.join(store.data_dir(), "saves")


def write_stash(card, layout_name, system, stem, core, entries, now=None, dry_run=False):
    """Copy entries into a new stash folder for the game and write its stash.json; returns the folder."""
    now = (now or datetime.datetime.now()).replace(microsecond=0)
    base = os.path.join(stash_root(), system, stem, f"{now.strftime('%Y%m%d-%H%M%S')}-{card}")
    path, n = base, 1
    while os.path.exists(path):
        n += 1
        path = f"{base}-{n}"
    if dry_run:
        return path
    os.makedirs(path)
    for e in entries:
        shutil.copy2(e["path"], os.path.join(path, e["name"]))
    store.write_json(os.path.join(path, "stash.json"),
                     {"system": system, "game": stem, "card": card, "layout": layout_name, "core": core,
                      "stashed": now.isoformat(), "files": [{"name": e["name"], "kind": e["kind"]} for e in entries]},
                     **store.PRETTY)
    return path


def load_stashes(systems=None):
    """Every readable stash as {"dir", **stash.json}, optionally only of those system ids; by game, then newest."""
    out = []
    for dirpath, _, files in os.walk(stash_root()):
        if "stash.json" not in files:
            continue
        try:
            with open(os.path.join(dirpath, "stash.json"), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or any(k not in data for k in STASH_KEYS):
            continue
        if systems is None or data["system"] in systems:
            out.append({"dir": dirpath, **data})
    out.sort(key=lambda s: s["stashed"], reverse=True)
    out.sort(key=lambda s: (s["game"].casefold(), s["system"]))
    return out


def target_dir(base, layout_name, layout, system, kind, core, retroarch_dir=None):
    """Folder on the card for a file of this kind; ValueError when the path needs a core and there is none."""
    template = layout["retroarch"]["saves" if kind == "save" else "states"]
    if "{core}" in template and not core:
        raise ValueError("needs a core")
    folder = system["folders"].get(layout_name)
    if "{system}" in template and not folder:
        raise ValueError("system has no folder in this layout")
    rel = template.format(system=folder, core=core)
    return os.path.join(_base(base, layout, retroarch_dir), *rel.split("/"))


def core_folders(base, layout, retroarch_dir=None):
    """Names of the core subfolders already holding saves or states (empty without {core} in the layout)."""
    root = _base(base, layout, retroarch_dir)
    names = set()
    for template in (layout["retroarch"]["saves"], layout["retroarch"]["states"]):
        if "{core}" not in template:
            continue
        parent = os.path.join(root, *template.split("{core}")[0].split("/"))
        if os.path.isdir(parent):
            names.update(c for c in os.listdir(parent) if os.path.isdir(os.path.join(parent, c)))
    return sorted(names)


def plan_apply(stash, base, layout_name, layout, system, core, retroarch_dir=None):
    """[(src, dst, "new" | "same" | "differs")] for copying a stash's files to the card."""
    plan = []
    for f in stash["files"]:
        src = os.path.join(stash["dir"], f["name"])
        dst = os.path.join(target_dir(base, layout_name, layout, system, f["kind"], core, retroarch_dir), f["name"])
        if not os.path.exists(dst):
            state = "new"
        else:
            state = "same" if filecmp.cmp(src, dst, shallow=False) else "differs"
        plan.append((src, dst, state))
    return plan

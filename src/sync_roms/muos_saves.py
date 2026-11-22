"""muOS's Pickles saves and states on a card, for `saves stash` and `saves apply`. Saves are
`sram/<core>[/<ROM dir>]/<stem>.srm|.rtc` and states `state/<core>[/<ROM dir>]/<stem>/` (`slot_N.state` and
`states.ini`, Pickles' own format) under the layout's `pickles` dir; `<ROM dir>` is the ROM's folder under `ROMS/`.
Files are copied as they are, to the same relative path."""
import os
import re

from . import saves

LAYOUT = "muos"


def _key(folder):
    """A folder name as muOS matches it to a system: case, spaces, `-`, `_` and `+` ignored."""
    return re.sub(r"[ \-_+]", "", folder).casefold()


def _root(base, layout):
    return os.path.join(base, *layout["pickles"]["dir"].split("/"))


def _files(top):
    """[(core, folder parts under the core, file name)] of every file under top/<core>/."""
    out = []
    if not os.path.isdir(top):
        return out
    for core in saves._listdir(top):
        if not os.path.isdir(os.path.join(top, core)):
            continue
        for dirpath, dirs, names in os.walk(os.path.join(top, core), followlinks=True):
            dirs.sort()
            parts = os.path.relpath(dirpath, os.path.join(top, core)).split(os.sep)
            parts = [] if parts == ["."] else parts
            out += [(core, parts, n) for n in sorted(names) if not n.startswith("._")]
    return out


def scan(base, layout, systems):
    """({(system, stem): [entry]}, skipped): the card's Pickles saves and states by game, each entry with its
    `core` and `rel` (its ROM dir, "" when there is none). A file under a ROM dir that is no system's muOS folder, or
    without one and with no single system holding a ROM of its name, counts toward skipped."""
    root = _root(base, layout)
    by_key = {}
    for s in systems:  # systems sharing a folder are one candidate: the first in systems order
        if s["folders"].get(LAYOUT):
            by_key.setdefault(_key(s["folders"][LAYOUT]), s["bucket"])
    stems = None
    games, skipped = {}, 0
    for sub, kind in (("sram", "save"), ("state", "state")):
        for core, parts, name in _files(os.path.join(root, sub)):
            if kind == "save":
                if not name.endswith((".srm", ".rtc")) or name[:-4] in ("", ".", ".."):
                    continue
                stem, rel_parts = name[:-4], parts
            else:
                if not parts:  # a state file not in a game's folder
                    skipped += 1
                    continue
                stem, rel_parts = parts[-1], parts[:-1]
            if rel_parts:
                system = by_key.get(_key(rel_parts[0]))
            else:
                if stems is None:
                    stems = saves.rom_stems(base, LAYOUT, layout, systems)
                found = stems.get(stem, set())
                folders = {s["folders"][LAYOUT] for s in systems if s["bucket"] in found}
                system = by_key.get(_key(next(iter(folders)))) if len(folders) == 1 else None
            if not system:
                skipped += 1
                continue
            path = os.path.join(root, sub, core, *parts, name)
            st = os.stat(path)
            games.setdefault((system, stem), []).append(
                {"path": path, "name": name, "kind": kind, "core": core, "rel": "/".join(rel_parts),
                 "size": st.st_size, "mtime": st.st_mtime})
    return games, skipped


def is_pickles(stash):
    """Whether a stash was made from Pickles files (its files record their ROM dir)."""
    return any("rel" in f for f in stash["files"])


def stash_rel(stash):
    """The ROM dir of a Pickles stash (one per stash), None for a RetroArch one."""
    return next((f["rel"] for f in stash["files"] if "rel" in f), None)


def plan_apply(stash, base, layout, system, core):
    """[(src, dst, "new" | "same" | "differs")] for copying a Pickles stash's files to the same relative paths on
    the card."""
    root = _root(base, layout)
    plan = []
    for f in stash["files"]:
        rel = [p for p in f.get("rel", "").split("/") if p]
        if f["kind"] == "save":
            folder = os.path.join(root, "sram", core, *rel)
        else:
            folder = os.path.join(root, "state", core, *rel, stash["game"])
        src, dst = os.path.join(stash["dir"], f["name"]), os.path.join(folder, f["name"])
        plan.append((src, dst, saves.file_state(src, dst)))
    return plan

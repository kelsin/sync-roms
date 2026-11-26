"""RetroArch saves and states on a card (muOS: Pickles ones, through muos_saves; an Android card over adb, through
android): reading them, stashing them in the data folder, copying them back (`saves stash` and `saves apply`)."""
import datetime
import filecmp
import json
import os
import re
import shutil

from . import adb, android, muos_saves, picker, store, ui

STATE = re.compile(r"^(?P<stem>.+)\.state(\d+|\.auto)?$")
STASH_KEYS = ("system", "game", "card", "layout", "core", "stashed", "files")


def classify(name):
    """(stem, kind) of a RetroArch file name (save, state or thumbnail), or None for anything else. A save is
    `.srm` or Gambatte's `.rtc` (a game's clock); macOS `._` files are none."""
    if name.startswith("._"):
        return None
    c = _classify(name)
    return c if c and c[0] not in ("", ".", "..") else None


def beside_roms(layout):
    """Whether the layout's RetroArch saves and states sit in its ROM folders (ROCKNIX): they are never ROMs there."""
    return layout.get("retroarch", {}).get("dir") == layout["roms_dir"]


def _classify(name):
    for ext in (".srm", ".rtc"):
        if name.endswith(ext):
            return name[:-4], "save"
    m = STATE.match(name)
    if m:
        return m.group("stem"), "state"
    if name.endswith(".png"):
        m = STATE.match(name[:-4])
        if m:
            return m.group("stem"), "thumbnail"
    return None


def _listdir(folder):
    """Sorted names in folder; a folder that can't be read is warned about and counts as empty."""
    try:
        return sorted(os.listdir(folder))
    except OSError as e:
        ui.warn(f"Can't read {folder}: {e.strerror or e}")
        return []


def broken_links(base, layout, retroarch_dir=None):
    """Paths on the way to the layout's saves and states folders (the RetroArch folder and each folder before a
    {core} or {system}) that exist but aren't folders, typically a symlink to somewhere not on this machine."""
    root = _base(base, layout, retroarch_dir)
    found = [root]
    for template in (layout["retroarch"]["saves"], layout["retroarch"]["states"]):
        path = root
        for part in template.split("/"):
            if "{" in part:
                break
            path = os.path.join(path, part)
            found.append(path)
    return sorted({p for p in found if os.path.lexists(p) and not os.path.isdir(p)})


def _broken_hint(paths):
    return (f"{', '.join(paths)} is a link to somewhere that isn't a folder here; pass the real folder with "
            "`--retroarch DIR`")


def _base(base, layout, retroarch_dir):
    return retroarch_dir or os.path.join(base, *filter(None, layout["retroarch"]["dir"].split("/")))


def rom_stems(base, layout_name, layout, systems, skip_saves=False):
    """{stem: {system ids}} of every file in the card's ROM folders (skip_saves: not RetroArch saves, states and
    thumbnails, which sit in the ROM folders on ROCKNIX)."""
    stems = {}
    for s in systems:
        folder = s["folders"].get(layout_name)
        if not folder:
            continue
        root = os.path.join(base, *layout["roms_dir"].split("/"), folder)
        for dirpath, dirs, files in os.walk(root, followlinks=True):
            dirs[:] = [d for d in dirs if d != ".media"]  # NextUI's art
            for f in files:
                if f.startswith("._") or (skip_saves and classify(f)):
                    continue
                stems.setdefault(os.path.splitext(f)[0], set()).add(s["bucket"])
    return stems


def minui_name(srm_name, rom_names):
    """MinUI's name for a RetroArch save: the ROM's full file name plus `.sav` ("Game.srm" -> "Game.gba.sav"). Among
    ROMs with that stem a playlist (.m3u) or cue sheet wins; None when there is none or several remain."""
    stem = srm_name[:-4] if srm_name.endswith(".srm") else srm_name
    found = [r for r in rom_names if os.path.splitext(r)[0] == stem]
    for ext in (".m3u", ".cue"):
        first = [r for r in found if r.lower().endswith(ext)]
        if first:
            found = first
            break
    return f"{found[0]}.sav" if len(found) == 1 else None


def retroarch_name(sav_name):
    """RetroArch's name for a MinUI save ("Game.gba.sav" -> "Game.srm"): the ROM's extension goes."""
    stem = sav_name[:-4] if sav_name.endswith(".sav") else sav_name
    return re.sub(r"\.[A-Za-z0-9]{1,5}$", "", stem) + ".srm"


def _minui(layout):
    return layout.get("save_naming") == "minui"


def rom_names(base, layout_name, layout, system):
    """File names in the card's ROM folder of one system."""
    folder = system["folders"].get(layout_name)
    if not folder:
        return []
    root = os.path.join(base, *layout["roms_dir"].split("/"), folder)
    names = []
    for _, dirs, files in os.walk(root, followlinks=True):
        dirs[:] = [d for d in dirs if not d.startswith(".")]  # NextUI's .media art
        names += [f for f in files if not f.startswith(".")]
    return names


def _folders(root, template, systems, layout_name):
    """[(folder, system id or None, core or None)] of a layout's saves or states path template; a {core} parent
    is listed first as a core-less folder (RetroArch with sort by core off)."""
    if "{tag}-{core}" in template:
        # a core folder per system: "<tag>-<core>" next to its siblings
        parts = template.split("/")
        parent = os.path.join(root, *parts[:-1])
        if not os.path.isdir(parent):
            return []
        names = _listdir(parent)
        return [(os.path.join(parent, n), s["bucket"], n[len(tag) + 1:])
                for s in systems if (tag := store.folder_tag(s["folders"].get(layout_name)))
                for n in names if n.startswith(f"{tag}-") and len(n) > len(tag) + 1
                and os.path.isdir(os.path.join(parent, n))]
    if "{core}" in template:
        parent = os.path.join(root, *template.split("{core}")[0].split("/"))
        if not os.path.isdir(parent):
            return []
        return [(parent, None, None)] + [(os.path.join(parent, c), None, c) for c in _listdir(parent)
                                         if os.path.isdir(os.path.join(parent, c))]
    if "{system}" in template:
        # a folder shared by several systems is scanned once, for the first in systems order
        return [(os.path.join(root, *template.format(system=s["folders"][layout_name]).split("/")),
                 s["bucket"], None) for s in systems if s["folders"].get(layout_name)]
    if "{tag}" in template:
        return [(os.path.join(root, *template.format(tag=store.folder_tag(s["folders"].get(layout_name))).split("/")),
                 s["bucket"], None) for s in systems if store.folder_tag(s["folders"].get(layout_name))]
    return [(os.path.join(root, *template.split("/")), None, None)]


def scan(base, layout_name, layout, systems, retroarch_dir=None):
    """({(system, stem): [entry]}, skipped): the card's RetroArch files by game. skipped counts files whose game
    isn't on the card."""
    root = _base(base, layout, retroarch_dir)
    ra = layout["retroarch"]
    in_rom_folders = beside_roms(layout)  # ROCKNIX: saves live in the ROM folders, so a ROM must be there
    stems = rom_stems(base, layout_name, layout, systems, skip_saves=in_rom_folders)
    folders = {s["bucket"]: s["folders"].get(layout_name) for s in systems}
    games, skipped, seen = {}, 0, set()
    for template in (ra["saves"], ra["states"]):
        rows = _folders(root, template, systems, layout_name)
        owners = {}
        for folder, system, _ in rows:
            owners.setdefault(folder, set()).add(system)
        for folder, system, core in rows:
            if folder in seen or not os.path.isdir(folder):
                continue
            seen.add(folder)
            # a NextUI tag folder (Saves/FBN) shared by systems with their own ROM folders: the ROM picks the system
            shared = owners[folder] if len({folders.get(b) for b in owners[folder]}) > 1 else None
            for name in _listdir(folder):
                path = os.path.join(folder, name)
                if _minui(layout) and system != "psx" and name.endswith(".sav"):
                    name = retroarch_name(name)
                c = classify(name)
                if not c or not os.path.isfile(path):
                    continue
                stem, kind = c
                if shared:  # a NextUI state keeps the ROM's extension ("Game.zip.state")
                    found = (stems.get(stem) or stems.get(retroarch_name(stem)[:-4], set())) & shared
                else:
                    found = {system} if system else stems.get(stem, set())
                    if system and in_rom_folders and system not in stems.get(stem, set()):
                        found = set()
                if len({folders[b] for b in found}) != 1:
                    skipped += 1
                    continue
                # systems sharing a ROM folder (WS, NGP) are one candidate: the first in systems order
                found = {next(s["bucket"] for s in systems if s["bucket"] in found)}
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
                      "stashed": now.isoformat(), "files": [_file(e) for e in entries]},
                     **store.PRETTY)
    return path


def _file(entry):
    """An entry as stash.json lists it; a Pickles one (muOS) also keeps its ROM dir and core."""
    f = {"name": entry["name"], "kind": entry["kind"]}
    if "rel" in entry:
        f.update(rel=entry["rel"], core=entry["core"])
    return f


def _unsafe(name):
    return name in ("", ".", "..") or any(c and c in name for c in ("/", os.sep, os.altsep))


def _bad_pickles(data):
    """Whether a stash's Pickles paths (each file's `rel`, its core) could leave the card's Pickles folder."""
    rels = [f["rel"] for f in data["files"] if "rel" in f]
    if not rels:
        return False
    return not isinstance(data["core"], str) or _unsafe(data["core"]) or _unsafe(data["game"]) \
        or any(not isinstance(r, str) or os.path.isabs(r) or "\\" in r
               or any(_unsafe(p) for p in r.split("/") if p) for r in rels)


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
        if not all(isinstance(data[k], str) for k in ("game", "system", "stashed")) \
                or not isinstance(data["files"], list) \
                or any(not isinstance(f, dict) or not isinstance(f.get("name"), str)
                       or any(c and c in f["name"] for c in ("/", os.sep, os.altsep)) for f in data["files"]) \
                or _bad_pickles(data):
            continue
        if systems is None or data["system"] in systems:
            out.append({"dir": dirpath, **data})
    out.sort(key=lambda s: s["stashed"], reverse=True)
    out.sort(key=lambda s: (store.sort_key(s["game"]), s["system"]))
    return out


def target_dir(base, layout_name, layout, system, kind, core, retroarch_dir=None):
    """Folder on the card for a file of this kind; ValueError when the path needs a core and there is none."""
    template = layout["retroarch"]["saves" if kind == "save" else "states"]
    if "{core}" in template and core is None:
        raise ValueError("needs a core")
    folder = system["folders"].get(layout_name)
    if "{system}" in template and not folder:
        raise ValueError("system has no folder in this layout")
    tag = store.folder_tag(folder)
    if "{tag}" in template and not tag:
        raise ValueError("system has no tag in this layout")
    rel = template.format(system=folder, core=core, tag=tag)  # core "": the {core} parent (sort by core off)
    return os.path.join(_base(base, layout, retroarch_dir), *[p for p in rel.split("/") if p])


def core_folders(base, layout, retroarch_dir=None):
    """Names of the core subfolders already holding saves or states (empty without {core} in the layout)."""
    root = _base(base, layout, retroarch_dir)
    names = set()
    for template in (layout["retroarch"]["saves"], layout["retroarch"]["states"]):
        if "{core}" not in template or "{tag}" in template:
            continue
        parent = os.path.join(root, *template.split("{core}")[0].split("/"))
        if os.path.isdir(parent):
            names.update(c for c in _listdir(parent) if os.path.isdir(os.path.join(parent, c)))
    return sorted(names)


def file_state(src, dst):
    """What copying src to dst would do: "new" with no dst, else "same" or "differs" by their bytes."""
    if not os.path.exists(dst):
        return "new"
    return "same" if filecmp.cmp(src, dst, shallow=False) else "differs"


def plan_apply(stash, base, layout_name, layout, system, core, retroarch_dir=None):
    """[(src, dst, "new" | "same" | "differs")] for copying a stash's files to the card."""
    plan, roms = [], None
    for f in stash["files"]:
        src = os.path.join(stash["dir"], f["name"])
        name = f["name"]
        if _minui(layout) and f["kind"] == "save" and system["bucket"] != "psx" and name.endswith(".srm"):
            roms = rom_names(base, layout_name, layout, system) if roms is None else roms
            renamed = minui_name(name, roms)
            if renamed:
                name = renamed
            else:
                several = sum(os.path.splitext(r)[0] == name[:-4] for r in roms) > 1
                ui.warn(f"{'several ROMs share the name of' if several else 'no ROM on the card for'} {name}; "
                        "copied under its RetroArch name")
        dst = os.path.join(target_dir(base, layout_name, layout, system, f["kind"], core, retroarch_dir), name)
        plan.append((src, dst, file_state(src, dst)))
    return plan


# --- saves stash / saves apply ------------------------------------------------------------------------

TYPE_CORE = "Type a name…"
NO_CORE = "No core folder (sort by core off)"


def card_setup(args):
    """(base, card name, its saved (device or None for Full, layout name), catalog) of the command's card: args.card
    (a folder, or a saved card's name found at /Volumes), else the current folder. Exits 2 when it is no saved card, has no usable layout or is no folder."""
    if args.card and not os.path.isdir(os.path.expanduser(args.card)) and os.sep not in args.card:
        base = os.path.join("/Volumes", args.card)
    else:
        base = os.path.abspath(os.path.expanduser(args.card or os.getcwd()))
    name = os.path.basename(base)
    cards = store.load_cards()
    if name not in cards:
        ui.fail(f"No card named {name!r}. Set it up with `sync-roms cards new {name} --device ID|full --layout NAME`", 2)
    catalog = store.load_catalog()
    setup = _saved_setup(cards, name, catalog)
    if not os.path.isdir(base):
        ui.fail(f"No folder {base}: give the card's mounted folder, e.g. `/Volumes/{name}`", 2)
    return base, name, setup, catalog


def _saved_setup(cards, name, catalog):
    setup = picker.saved_setup(cards[name], catalog["devices"], catalog["layouts"], name)
    if not setup:
        ui.fail(f"{name!r} has no usable layout. Set it with `sync-roms cards set {name} --layout NAME`", 2)
    return setup


def _card(args, what):
    """(base, card name, layout name, layout, device or None for Full, catalog, android.Session or None) of the
    command's card: a folder (args.card, else the current folder named after a card), else an Android card over adb
    (args.card naming it, else the device picked), staged in the session's base. Exits 2 when it isn't a set-up card,
    or without a terminal; 1 when the device's connection is lost."""
    cards = store.load_cards()
    if args.card and (os.path.isdir(args.card) or args.card not in cards) or \
            not args.card and os.path.basename(os.getcwd()) in cards:
        base, name, (device, layout_name), catalog = card_setup(args)
        if not ui.has_terminal():
            ui.fail(f"`saves {what}` needs a terminal to pick from", 2)
        return base, name, layout_name, catalog["layouts"][layout_name], device, catalog, None
    if args.card and not android.is_android(cards[args.card]):
        ui.fail(f"{args.card!r} isn't an Android card: pass its mounted folder", 2)
    if args.retroarch:
        ui.fail("--retroarch only applies to a mounted card", 2)
    catalog = store.load_catalog()
    if args.card:
        _saved_setup(cards, args.card, catalog)
    if not ui.has_terminal():
        ui.fail(f"`saves {what}` needs a terminal to pick from", 2)
    if not args.card:
        adb.require(mounted=True)
    try:
        target = android.resolve(args.card, cards, catalog["layouts"]["esde"]["roms_dir"])
    except adb.AdbError as e:
        ui.fail(f"Lost the connection to the device: {e}", 1)
    device, layout_name = _saved_setup(cards, target.card, catalog)
    try:
        session = android.open_session(target, catalog["layouts"][layout_name], layout_name, catalog["systems"])
    except adb.AdbError as e:
        ui.fail(f"Lost the connection to {target.model or target.serial}: {e}", 1)
    args.retroarch = session.retroarch_dir
    return session.base, target.card, layout_name, session.layout, device, catalog, session


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _counts(kinds):
    """"N saves · M states" of a list of kinds (thumbnails count as neither)."""
    return f"{_plural(kinds.count('save'), 'save')} · {_plural(kinds.count('state'), 'state')}"


def _states_note(cores):
    """Print that states only load in the core they came from, for the cores (None: unknown) of stashes with states."""
    known = sorted(c for c in cores if c)
    if known:
        print(ui.yellow(f"⚠️  States only load in the core they came from: {', '.join(known)}"))
    if None in cores:
        print(ui.yellow("⚠️  States only load in the core they were made with"))


def _rel_prefix(entry):
    """"<ROM dir>/" of a Pickles entry with one, else ""."""
    return f"{entry['rel']}/" if entry.get("rel") else ""


FILES_SORT = picker.Sort(("name",))  # the files lists' sort, for the run


def _pad(cells):
    """A row's extras with the two spaces between columns the lists use."""
    return [("  " + text, color) for text, color in cells]


def _when(mtime):
    return datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


@picker.one_app
def pick_stash(games, names):
    """The entries to stash, picked as games (none on) then their files (all on); None on Esc or nothing picked."""
    from . import gamecols  # gamecols imports modules that import this one
    keys = sorted(games, key=lambda k: (store.sort_key(k[1]), names.get(k[0], k[0])))
    cores = [", ".join(sorted({e["core"] for e in games[k] if e["core"]})) for k in keys]
    cols = gamecols.GameColumns([(system, stem, None) for system, stem in keys],
                                extra_columns=[picker.Column("kinds", "Saves"), picker.Column("core", "Core", True)],
                                extra_values=lambda i, col: cores[i] or None if col == "core" else None)
    extras = [_pad([(_counts([e["kind"] for e in games[k]]), ""), (core, "cyan")]) for k, core in zip(keys, cores)]
    state = picker.filter_list("💾 Games to stash", [stem for _, stem in keys], multi=True, initial=[False] * len(keys),
                               esc_asks=False, hint="Space toggle · Enter pick their files", **cols.kwargs(extras))
    chosen = [k for k, on in zip(keys, state or []) if on]
    if not chosen:
        return None
    rows = [(k, e) for k in chosen for e in games[k]]
    extras = [_pad([(e["kind"], "dim"), (ui.human_size(e["size"]), ""), (_when(e["mtime"]), "dim"), (e["core"] or "", "cyan")])
              for _, e in rows]
    values = {"name": None, "kind": lambda e: e["kind"], "size": lambda e: e["size"], "modified": lambda e: _when(e["mtime"]),
              "core": lambda e: e["core"] or None}
    state = picker.filter_list("💾 Files to stash", [f"{k[1]} · {_rel_prefix(e)}{e['name']}" for k, e in rows], multi=True,
                               initial=[True] * len(rows), esc_asks=False, extras=extras,
                               hint="Space toggle · Enter stash", sort=FILES_SORT,
                               columns=[picker.Column("name", "File", True), picker.Column("kind", "Kind", True),
                                        picker.Column("size", "Size", True, descending=True),
                                        picker.Column("modified", "Modified", True, descending=True),
                                        picker.Column("core", "Core", True)],
                               sort_value=lambda i, col: values[col](rows[i][1]) if values[col] else None)
    picked = [(k, e) for (k, e), on in zip(rows, state or []) if on]
    return picked or None


def stash_command(args):
    """`saves stash [CARD]`: copy picked RetroArch (muOS: Pickles) saves and states off the card into the stash
    folder."""
    base, card, layout_name, layout, _, catalog, session = _card(args, "stash")
    try:
        return _stash(args, base, card, layout_name, layout, catalog)
    finally:
        if session:
            session.close()


def _stash(args, base, card, layout_name, layout, catalog):
    systems = catalog["systems"]
    pickles = "pickles" in layout
    if pickles:
        if args.retroarch:
            ui.warn("--retroarch is ignored on muOS cards")
        games, skipped = muos_saves.scan(base, layout, systems)
        note = ui.dim(f"  skipped {_plural(skipped, 'file')} whose game isn't on the card (no system's folder, "
                      "or no single ROM of its name)")
    else:
        games, skipped = scan(base, layout_name, layout, systems, args.retroarch)
        note = ui.dim(f"  skipped {_plural(skipped, 'file')} whose game isn't on the card (no ROM, or in several systems)")
        broken = broken_links(base, layout, args.retroarch)
        if broken:
            ui.warn(_broken_hint(broken))
    if not games:
        print(ui.yellow(f"↩️  No {'Pickles' if pickles else 'RetroArch'} saves or states on {card}"))
        if skipped:
            print(note)
        return 0
    picked = pick_stash(games, {s["bucket"]: s.get("name", s["bucket"]) for s in systems})
    if not picked:
        print(ui.yellow("↩️  Nothing stashed"))
        return 0
    groups = {}
    for (system, stem), e in picked:
        # a Pickles stash holds one ROM dir: same-named saves of two folders stay apart
        groups.setdefault((system, stem, e["core"], e.get("rel")), []).append(e)
    for (system, stem, core, _), entries in groups.items():
        folder = write_stash(card, layout_name, system, stem, core, entries, dry_run=args.dry_run)
        if args.dry_run:
            print(ui.dim(f"  {folder}: {', '.join(e['name'] for e in entries)}"))
    done = f"{len(picked)} file(s) of {len({(k[0], k[1], k[3]) for k in groups})} game(s)"
    if args.dry_run:
        print(ui.yellow(f"🧪 Would stash {done} to {stash_root()}"))
        return 0
    print(ui.green(f"💾 Stashed {done} to {stash_root()}"))
    if skipped:
        print(note)
    _states_note({core for (_, _, core, _), entries in groups.items() if any(e["kind"] == "state" for e in entries)})
    return 0


def _target_system(stash, by_id, layouts, stems):
    """The system a stash goes to on the card: among its own system and those sharing its ROM folder in the stash's
    layout (WS, NGP), the one whose folder on the card has a ROM of the stash's game; else its own. None when its
    system is gone."""
    own = by_id.get(stash["system"])
    if not own:
        return None
    folder = own["folders"].get(stash["layout"]) if stash["layout"] in layouts else None
    candidates = [own] + [s for s in by_id.values()
                          if folder and s is not own and s["folders"].get(stash["layout"]) == folder]
    found = stems.get(stash["game"], set())
    return next((s for s in candidates if s["bucket"] in found), own)


@picker.one_app
def pick_apply(labels, extras, games):
    """Indexes of the picked stashes; picking two of one game (`games`, per row) keeps the list open. None on Esc or
    nothing picked."""
    from . import gamecols  # gamecols imports modules that import this one
    session = {}
    while True:
        cols = gamecols.GameColumns([(system, stem, None) for system, stem, _ in games],
                                extra_columns=[picker.Column("from", "From"), picker.Column("stashed", "Stashed", True, descending=True),
                                               picker.Column("kinds", "Saves"), picker.Column("core", "Core"),
                                               picker.Column("found", "On card"), picker.Column("note", "Note")],
                                extra_values=lambda i, col: extras[i][1][0].strip() if col == "stashed" else None)
        state = picker.filter_list("📥 Saves to apply", labels, multi=True, initial=[False] * len(labels),
                                   esc_asks=False, session=session, hint="Space toggle · Enter apply", **cols.kwargs(extras))
        chosen = [i for i, on in enumerate(state or []) if on]
        twice = sorted({games[i][1] for i in chosen if sum(games[j] == games[i] for j in chosen) > 1})
        if not twice:
            return chosen or None
        text = f"Pick one stash per game: {', '.join(twice)}"
        if not picker.queue_note(text):
            print(ui.yellow(f"⚠️  {text}"))


def _ask_core(base, layout, system, retroarch_dir):
    """The core folder for stashes made without one: one on the card, a typed one, or "" for none; None skips them."""
    if ui.ASSUME_YES or not ui.has_terminal():
        return None
    found = core_folders(base, layout, retroarch_dir)
    # a "<tag>-<core>" folder always has a core, so there is no sort-by-core-off choice
    options = [TYPE_CORE] if "{tag}" in layout["retroarch"]["states"] else [TYPE_CORE, NO_CORE]
    i = picker.filter_list(f"📁 Core folder for the {system.get('name', system['bucket'])} saves", found + options,
                           hint="Enter pick · Esc skip")
    if i is None:
        return None
    if i == len(found) + 1:
        return ""
    if i == len(found):
        return ui.ask("📁 Core folder name: ").strip() or None
    return found[i]


def apply_command(args):
    """`saves apply [CARD]`: copy picked stashes into the card's RetroArch folders for its layout (muOS: Pickles
    folders, at the paths they were stashed from; an Android card: then pushed to the device)."""
    base, card, layout_name, layout, device, catalog, session = _card(args, "apply")
    try:
        return _apply(args, base, card, layout_name, layout, device, catalog, session)
    finally:
        if session:
            session.close()


def _apply(args, base, card, layout_name, layout, device, catalog, session):
    shown = session.remote if session else (lambda path: path)  # a path as the user knows it
    pickles = "pickles" in layout  # Pickles and RetroArch states differ: a stash only goes back to its own kind
    if pickles and args.retroarch:
        ui.warn("--retroarch is ignored on muOS cards")
    by_id = {s["bucket"]: s for s in catalog["systems"]}
    stems = rom_stems(base, layout_name, layout, catalog["systems"], skip_saves=beside_roms(layout))
    rows = []
    for stash in load_stashes():
        if muos_saves.is_pickles(stash) != pickles:
            continue
        system = _target_system(stash, by_id, catalog["layouts"], stems)
        if system and store.system_applies(system, device, layout_name):
            rows.append((stash, system))
    if not rows:
        print(ui.yellow(f"↩️  No stashed saves for the systems {card} syncs (in {stash_root()})"))
        return 0
    extras = [_pad([(f"from {stash['card']}", ""),
               (stash["stashed"][:16].replace("T", " "), "dim"), (_counts([f["kind"] for f in stash["files"]]), ""),
               (stash["core"] or "", "cyan"),
               ("" if system["bucket"] in stems.get(stash["game"], ()) else "not on card", "red"),
               (stash.get("note", ""), "dim")])
              for stash, system in rows]
    rels = [muos_saves.stash_rel(stash) for stash, _ in rows]  # None: RetroArch; a game per ROM dir on muOS
    chosen = pick_apply([stash["game"] + (f" · {rel}" if rel else "") for (stash, _), rel in zip(rows, rels)], extras,
                        [(system["bucket"], stash["game"], rel) for (stash, system), rel in zip(rows, rels)])
    if not chosen:
        print(ui.yellow("↩️  Nothing applied"))
        return 0
    broken = [] if pickles else broken_links(base, layout, args.retroarch)
    if broken:
        ui.fail(_broken_hint(broken), 2)
    cores, plan = {}, []
    for i in chosen:
        stash, system = rows[i]
        present = [f for f in stash["files"] if os.path.isfile(os.path.join(stash["dir"], f["name"]))]
        for f in stash["files"]:
            if f not in present:
                ui.warn(f"Skipped {f['name']} of {stash['game']}: missing from {stash['dir']}")
        if not present:
            continue
        stash = dict(stash, files=present)
        core = stash["core"]
        needs_core = not pickles and any("{core}" in layout["retroarch"]["saves" if f["kind"] == "save" else "states"]
                                         for f in present)
        if core is None and needs_core:
            if system["bucket"] not in cores:
                cores[system["bucket"]] = _ask_core(base, layout, system, args.retroarch)
            core = cores[system["bucket"]]
            if core is None:
                ui.warn(f"Skipped {stash['game']}: no core folder for its saves")
                continue
        plan.append((stash, muos_saves.plan_apply(stash, base, layout, system, core) if pickles
                     else plan_apply(stash, base, layout_name, layout, system, core, args.retroarch)))
    differs = [dst for _, steps in plan for _, dst, state in steps if state == "differs"]
    same = sum(state == "same" for _, steps in plan for _, _, state in steps)
    overwrite = args.dry_run
    if differs and not args.dry_run:
        print(ui.yellow(f"⚠️  {len(differs)} file(s) on {card} differ from the stash:"))
        for dst in differs:
            print(ui.dim(f"  {shown(dst)}"))
        overwrite = ui.confirm("Overwrite them?")
    copied, games, state_cores, written = 0, 0, set(), []
    for stash, steps in plan:
        todo = [(f, src, dst) for f, (src, dst, state) in zip(stash["files"], steps)
                if state == "new" or state == "differs" and overwrite]
        for f, src, dst in todo:
            if args.dry_run:
                print(ui.dim(f"  {src} → {shown(dst)}"))
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            written.append(dst)
        copied += len(todo)
        games += bool(todo)
        if any(f["kind"] == "state" for f, _, _ in todo):
            state_cores.add(stash["core"])
    failed = []
    if session and written:
        android.wait_closed(session.target.serial, session.pkg)  # RetroArch may have been reopened during the pickers
        failed = session.push(written)
    for path, error in failed:
        ui.warn(f"Couldn't copy {path} to the device: {error}")
    done = f"{copied} file(s) of {games} game(s) to {card}"
    if args.dry_run:
        print(ui.yellow(f"🧪 Would apply {done}" + (f" ({len(differs)} overwriting a different file, asked first)"
                                                    if differs else "")))
    else:
        print(ui.green(f"💾 Applied {done}"))
    if same:
        print(ui.dim(f"  {same} identical file(s) skipped"))
    if differs and not overwrite:
        print(ui.dim(f"  {len(differs)} different file(s) kept"))
    _states_note(state_cores)
    if failed:
        ui.fail(f"{len(failed)} file(s) not copied to {card}", 1)
    return 0

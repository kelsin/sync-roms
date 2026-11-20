"""RetroArch saves and states on a card: reading them, stashing them in the data folder, copying them back
(`saves stash` and `saves apply`)."""
import datetime
import filecmp
import json
import os
import re
import shutil

from . import picker, store, ui

STATE = re.compile(r"^(?P<stem>.+)\.state(\d+|\.auto)?$")
STASH_KEYS = ("system", "game", "card", "layout", "core", "stashed", "files")


def classify(name):
    """(stem, kind) of a RetroArch file name (save, state or thumbnail), or None for anything else. A save is
    `.srm` or Gambatte's `.rtc` (a game's clock); macOS `._` files are none."""
    if name.startswith("._"):
        return None
    c = _classify(name)
    return c if c and c[0] not in ("", ".", "..") else None


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
                if f.startswith("._"):
                    continue
                stems.setdefault(os.path.splitext(f)[0], set()).add(s["bucket"])
    return stems


def _folders(root, template, systems, layout_name):
    """[(folder, system id or None, core or None)] of a layout's saves or states path template; a {core} parent
    is listed first as a core-less folder (RetroArch with sort by core off)."""
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
    return [(os.path.join(root, *template.split("/")), None, None)]


def scan(base, layout_name, layout, systems, retroarch_dir=None):
    """({(system, stem): [entry]}, skipped): the card's RetroArch files by game. skipped counts files whose game
    isn't on the card."""
    root = _base(base, layout, retroarch_dir)
    ra = layout["retroarch"]
    stems = rom_stems(base, layout_name, layout, systems)
    folders = {s["bucket"]: s["folders"].get(layout_name) for s in systems}
    games, skipped, seen = {}, 0, set()
    for template in (ra["saves"], ra["states"]):
        for folder, system, core in _folders(root, template, systems, layout_name):
            if folder in seen or not os.path.isdir(folder):
                continue
            seen.add(folder)
            for name in _listdir(folder):
                path = os.path.join(folder, name)
                c = classify(name)
                if not c or not os.path.isfile(path):
                    continue
                stem, kind = c
                found = {system} if system else stems.get(stem, set())
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
        if not all(isinstance(data[k], str) for k in ("game", "system", "stashed")) \
                or not isinstance(data["files"], list) \
                or any(not isinstance(f, dict) or not isinstance(f.get("name"), str)
                       or any(c and c in f["name"] for c in ("/", os.sep, os.altsep)) for f in data["files"]):
            continue
        if systems is None or data["system"] in systems:
            out.append({"dir": dirpath, **data})
    out.sort(key=lambda s: s["stashed"], reverse=True)
    out.sort(key=lambda s: (s["game"].casefold(), s["system"]))
    return out


def target_dir(base, layout_name, layout, system, kind, core, retroarch_dir=None):
    """Folder on the card for a file of this kind; ValueError when the path needs a core and there is none."""
    template = layout["retroarch"]["saves" if kind == "save" else "states"]
    if "{core}" in template and core is None:
        raise ValueError("needs a core")
    folder = system["folders"].get(layout_name)
    if "{system}" in template and not folder:
        raise ValueError("system has no folder in this layout")
    rel = template.format(system=folder, core=core)  # core "": the {core} parent (sort by core off)
    return os.path.join(_base(base, layout, retroarch_dir), *[p for p in rel.split("/") if p])


def core_folders(base, layout, retroarch_dir=None):
    """Names of the core subfolders already holding saves or states (empty without {core} in the layout)."""
    root = _base(base, layout, retroarch_dir)
    names = set()
    for template in (layout["retroarch"]["saves"], layout["retroarch"]["states"]):
        if "{core}" not in template:
            continue
        parent = os.path.join(root, *template.split("{core}")[0].split("/"))
        if os.path.isdir(parent):
            names.update(c for c in _listdir(parent) if os.path.isdir(os.path.join(parent, c)))
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


# --- saves stash / saves apply ------------------------------------------------------------------------

TYPE_CORE = "Type a name…"
NO_SAVES = "saves aren't supported for muOS yet"  # the muOS layout has no RetroArch folder in it
NO_CORE = "No core folder (sort by core off)"


def _card(args, what):
    """(base, card name, layout name, layout, device or None for Full, catalog) of the command's card; exits 2 when
    it isn't a set-up card, or without a terminal."""
    base = os.path.abspath(args.card or os.getcwd())
    name = os.path.basename(base)
    cards = store.load_cards()
    if name not in cards:
        ui.fail(f"No card named {name!r}. Set it up with `sync-roms cards new {name} --device ID|full --layout NAME`", 2)
    catalog = store.load_catalog()
    setup = picker.saved_setup(cards[name], catalog["devices"], catalog["layouts"], name)
    if not setup:
        ui.fail(f"{name!r} has no usable layout. Set it with `sync-roms cards set {name} --layout NAME`", 2)
    if not os.path.isdir(base):
        ui.fail(f"No folder {base}", 2)
    if not ui.has_terminal():
        ui.fail(f"`saves {what}` needs a terminal to pick from", 2)
    device, layout_name = setup
    return base, name, layout_name, catalog["layouts"][layout_name], device, catalog


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


@picker.one_app
def pick_stash(games, names):
    """The entries to stash, picked as games (none on) then their files (all on); None on Esc or nothing picked."""
    keys = sorted(games, key=lambda k: (k[1].casefold(), names.get(k[0], k[0])))
    extras = [[(names.get(system, system), "dim"), (_counts([e["kind"] for e in games[(system, stem)]]), ""),
               (", ".join(sorted({e["core"] for e in games[(system, stem)] if e["core"]})), "cyan")]
              for system, stem in keys]
    state = picker.filter_list("💾 Games to stash", [stem for _, stem in keys], multi=True, initial=[False] * len(keys),
                               esc_asks=False, extras=extras, hint="Space toggle · Enter pick their files")
    chosen = [k for k, on in zip(keys, state or []) if on]
    if not chosen:
        return None
    rows = [(k, e) for k in chosen for e in games[k]]
    extras = [[(e["kind"], "dim"), (ui.human_size(e["size"]), ""),
               (datetime.datetime.fromtimestamp(e["mtime"]).strftime("%Y-%m-%d %H:%M"), "dim"), (e["core"] or "", "cyan")]
              for _, e in rows]
    state = picker.filter_list("💾 Files to stash", [f"{k[1]} · {e['name']}" for k, e in rows], multi=True,
                               initial=[True] * len(rows), esc_asks=False, extras=extras,
                               hint="Space toggle · Enter stash")
    picked = [(k, e) for (k, e), on in zip(rows, state or []) if on]
    return picked or None


def stash_command(args):
    """`saves stash [CARD]`: copy picked RetroArch saves and states off the card into the stash folder."""
    base, card, layout_name, layout, _, catalog = _card(args, "stash")
    if "retroarch" not in layout:
        ui.warn(NO_SAVES)
        return 1
    systems = catalog["systems"]
    games, skipped = scan(base, layout_name, layout, systems, args.retroarch)
    note = ui.dim(f"  skipped {_plural(skipped, 'file')} whose game isn't on the card (no ROM, or in several systems)")
    broken = broken_links(base, layout, args.retroarch)
    if broken:
        ui.warn(_broken_hint(broken))
    if not games:
        print(ui.yellow(f"↩️  No RetroArch saves or states on {card}"))
        if skipped:
            print(note)
        return 0
    picked = pick_stash(games, {s["bucket"]: s.get("name", s["bucket"]) for s in systems})
    if not picked:
        print(ui.yellow("↩️  Nothing stashed"))
        return 0
    groups = {}
    for (system, stem), e in picked:
        groups.setdefault((system, stem, e["core"]), []).append(e)
    for (system, stem, core), entries in groups.items():
        folder = write_stash(card, layout_name, system, stem, core, entries, dry_run=args.dry_run)
        if args.dry_run:
            print(ui.dim(f"  {folder}: {', '.join(e['name'] for e in entries)}"))
    done = f"{len(picked)} file(s) of {len({k[:2] for k in groups})} game(s)"
    if args.dry_run:
        print(ui.yellow(f"🧪 Would stash {done} to {stash_root()}"))
        return 0
    print(ui.green(f"💾 Stashed {done} to {stash_root()}"))
    if skipped:
        print(note)
    _states_note({core for (_, _, core), entries in groups.items() if any(e["kind"] == "state" for e in entries)})
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
    session = {}
    while True:
        state = picker.filter_list("📥 Saves to apply", labels, multi=True, initial=[False] * len(labels),
                                   esc_asks=False, extras=extras, session=session, hint="Space toggle · Enter apply")
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
    i = picker.filter_list(f"📁 Core folder for the {system.get('name', system['bucket'])} saves", found + [TYPE_CORE, NO_CORE],
                           hint="Enter pick · Esc skip")
    if i is None:
        return None
    if i == len(found) + 1:
        return ""
    if i == len(found):
        return ui.ask("📁 Core folder name: ").strip() or None
    return found[i]


def apply_command(args):
    """`saves apply [CARD]`: copy picked stashes into the card's RetroArch folders for its layout."""
    base, card, layout_name, layout, device, catalog = _card(args, "apply")
    if "retroarch" not in layout:
        ui.warn(NO_SAVES)
        return 1
    by_id = {s["bucket"]: s for s in catalog["systems"]}
    stems = rom_stems(base, layout_name, layout, catalog["systems"])
    rows = []
    for stash in load_stashes():
        system = _target_system(stash, by_id, catalog["layouts"], stems)
        if system and store.system_applies(system, device, layout_name):
            rows.append((stash, system))
    if not rows:
        print(ui.yellow(f"↩️  No stashed saves for the systems {card} syncs (in {stash_root()})"))
        return 0
    extras = [[(system.get("name", system["bucket"]), "dim"), (f"from {stash['card']}", ""),
               (stash["stashed"][:16].replace("T", " "), "dim"), (_counts([f["kind"] for f in stash["files"]]), ""),
               (stash["core"] or "", "cyan"),
               ("" if system["bucket"] in stems.get(stash["game"], ()) else "not on card", "red")]
              for stash, system in rows]
    chosen = pick_apply([stash["game"] for stash, _ in rows], extras,
                        [(system["bucket"], stash["game"]) for stash, system in rows])
    if not chosen:
        print(ui.yellow("↩️  Nothing applied"))
        return 0
    broken = broken_links(base, layout, args.retroarch)
    if broken:
        ui.fail(_broken_hint(broken), 2)
    needs_core = any("{core}" in layout["retroarch"][k] for k in ("saves", "states"))
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
        if core is None and needs_core:
            if system["bucket"] not in cores:
                cores[system["bucket"]] = _ask_core(base, layout, system, args.retroarch)
            core = cores[system["bucket"]]
            if core is None:
                ui.warn(f"Skipped {stash['game']}: no core folder for its saves")
                continue
        plan.append((stash, plan_apply(stash, base, layout_name, layout, system, core, args.retroarch)))
    differs = [dst for _, steps in plan for _, dst, state in steps if state == "differs"]
    same = sum(state == "same" for _, steps in plan for _, _, state in steps)
    overwrite = args.dry_run
    if differs and not args.dry_run:
        print(ui.yellow(f"⚠️  {len(differs)} file(s) on {card} differ from the stash:"))
        for dst in differs:
            print(ui.dim(f"  {dst}"))
        overwrite = ui.confirm("Overwrite them?", default=False)
    copied, games, state_cores = 0, 0, set()
    for stash, steps in plan:
        todo = [(f, src, dst) for f, (src, dst, state) in zip(stash["files"], steps)
                if state == "new" or state == "differs" and overwrite]
        for f, src, dst in todo:
            if args.dry_run:
                print(ui.dim(f"  {src} → {dst}"))
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        copied += len(todo)
        games += bool(todo)
        if any(f["kind"] == "state" for f, _, _ in todo):
            state_cores.add(stash["core"])
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
    return 0

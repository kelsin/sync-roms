#!/usr/bin/env python3
"""Download ROMs and BIOS files from the roms bucket."""
import argparse
import curses
import json
import mimetypes
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from xml.sax.saxutils import escape, unescape

try:  # optional: downloads in-process instead of one `aws` process per file
    import boto3
    from botocore.config import Config
except ImportError:
    boto3 = None

BUCKET = None  # set by ensure_bucket() from settings.json
PROFILE = os.environ.get("ROMS_PROFILE", "roms-readonly")
WRITE_PROFILE = os.environ.get("ROMS_WRITE_PROFILE", "roms")
WORKERS = 8
MAX_MISSING_SHOWN = 5
MIRROR_MARKER = ".sync-roms-mirror"  # only folders holding this file are ever written to or pruned as a mirror
_mirror_root = None  # set once a sync reads from the local mirror instead of the bucket

_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ


def c(code, text):
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def bold(t): return c("1", t)
def dim(t): return c("2", t)
def red(t): return c("31", t)
def green(t): return c("32", t)
def yellow(t): return c("33", t)
def cyan(t): return c("36", t)


def help_text():
    return f"""
{bold('🎮 sync-roms')} — download ROMs and BIOS files from your S3 bucket

{bold('USAGE')}
  {green('sync-roms.py')} [{yellow('--dry-run')}] [{cyan('BASE_DIR')}]   {dim('(no folder: BASE_DIR is the current directory)')}

{bold('ARGUMENTS')}
  {cyan('BASE_DIR')}   📦 the card or folder root. The chosen layout decides the folders inside it
              {dim('(ES-DE ROMs/ BIOS/, Knulli roms/ bios/, Onion Roms/ BIOS/)')}

  Missing folders are created after you confirm; if they can't be created
  (no permission) the script stops before asking.

{bold('OPTIONS')}
  {yellow('-n, --dry-run')}   show what would be downloaded, download nothing
  {yellow('-e, --edit')}      ✏️  add/remove games in your local games.json (type to filter), then save it
                      {dim('(no folders needed; saves ~/.sync-roms/games.json)')}
  {yellow('-a, --ask')}           ❓ confirm the saved settings (device and layout, Android media folders) instead of using them silently;
                      answering no asks the question again and saves the new answer
  {yellow('-u, --upload-scrapes')} [{cyan('BASE_DIR')}]   ☁️  upload BASE_DIR/ES-DE scraped data (metadata, media, themes, collections,
                      settings) to the bucket's scrapes/ folder, merging with what's there
                      {dim('(only the safe-to-share metadata fields are kept; uploads with the ROMS_WRITE_PROFILE profile)')}
  {yellow('-c, --clean-scrapes')}   🧹 remove scrapes/ media and metadata for ROMs that aren't in the bucket at all (asks first, no folder needed)
  {yellow('--mirror')} [{cyan('DIR')}]   🪞 make or refresh a local copy of everything the game lists reference (ROMs, BIOS, scraped data); files that are
                      no longer referenced are deleted, a rerun with nothing changed downloads nothing (no DIR: the saved mirror)
  {yellow('--use-mirror')} {cyan('DIR')}   🪞 --mirror DIR, then save DIR so every sync refreshes it first and copies from it instead of the bucket
  {yellow('--clear-mirror')}   forget the saved mirror (its files stay)
  {yellow('--devices')}       📋 list the supported devices with their chip and how many systems each one gets, then exit
  {yellow('-h, --help')}      show this screen

  {dim('When it finishes (not on --dry-run), a .metadata_never_index file is created in BASE_DIR and its .fseventsd folder is emptied and given a no_log file (any OS); on a Mac, dot_clean then runs on BASE_DIR.')}
  {dim('ES-DE layout: files in the Android media folders (Alarms, DCIM, Download, Music, Pictures...) are removed and a .nomedia added')}
  {dim('to each, after asking once per card name; the answer (always/never) is saved in the user data folder and used without asking (--ask confirms it).')}
  {dim('If dot_clean fails, Spotlight is turned off for BASE_DIR with sudo mdutil (asks for your password) and dot_clean is retried.')}

{bold('FLOW')}
  1️⃣  Pick a device (its recommended systems come from the repo's device-systems.json, plus your add/remove overlay), or {bold('Full')} (every system),
      then a folder layout (the device's default is highlighted). Type to filter, enter continues, esc goes back.
      The choice is remembered per BASE_DIR folder name (in the user data folder) and used without asking next
      time. With --ask it is confirmed first; answer n to pick again.
  2️⃣  Toggle systems on/off (for a device, its recommended systems start on; otherwise systems whose folder already has files start on, the rest off; systems with no ROMs are hidden, press e shows them last)
  3️⃣  ROMs download, then BIOS for the chosen systems
  4️⃣  Scraped data (media, descriptions...) for the chosen systems' games is installed from the bucket's scrapes/ folder
      for the layout: ES-DE (ES-DE/ folder), Knulli (images/videos/manuals and gamelist.xml) or Onion (Imgs/ and
      miyoogamelist.xml). ES-DE also gets its themes, collections and the shared settings every time.
      Then media on the card for ROMs the card doesn't have is removed, for every system, no questions asked.

{bold('PICKER KEYS')}
  {yellow('↑/↓ j/k')} move   {yellow('PgUp/PgDn')} page   {yellow('space/tab')} toggle
  {yellow('a')} all on   {yellow('n')} all off   {yellow('e')} show/hide 0-ROM systems
  {yellow('enter')} confirm   {yellow('q')} quit

{bold('ENVIRONMENT')}
  {yellow('ROMS_PROFILE')}   aws profile to use (default: roms-readonly)
  {yellow('ROMS_WRITE_PROFILE')}   aws profile used to upload and clean scrapes (default: roms)
  {yellow('NO_COLOR')}       disable colors

{bold('NOTES')}
  ⚡ Files already present locally with the same size are skipped.
  🗑️  Local ROMs no longer in a chosen system's list are listed and, after you
     confirm (default no), deleted. Other systems' folders and BIOS are never touched.
     Frontend files are ignored: dotfiles, ES-DE systeminfo.txt/noload.txt, Knulli _info.txt,
     gamelist.xml and images/ videos/ manuals/ folders, Onion miyoogamelist.xml and Imgs/, Thumbs.db.
  📄 games.json lives in ~/.sync-roms/ (copied from the repo's version on first run) and is never read from the
     bucket. Optional ~/.sync-roms/device-systems.json adjusts a device's recommended systems:
     {"miyoo-flip-v2": {"add": ["psx"], "remove": ["gba"]}}
"""


def aws(*args, profile=None):
    cmd = ["aws", "--profile", profile or PROFILE, *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


REPO_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PERSONAL_FILES = ("games.json",)  # per-user, in data_dir(); never read from the bucket


def repo_json(name):
    with open(os.path.join(REPO_DATA, name + ".json")) as f:
        return json.load(f)


def personal_json(name):
    with open(os.path.join(data_dir(), name)) as f:
        return json.load(f)


def seed_personal_files():
    """Give the user their own copy of each personal file, starting from the repo's version."""
    os.makedirs(data_dir(), exist_ok=True)
    for name in PERSONAL_FILES:
        dest = os.path.join(data_dir(), name)
        if not os.path.exists(dest):
            shutil.copyfile(os.path.join(REPO_DATA, name), dest)


def apply_games(systems, games):
    """Attach each system's games from games.json. An entry of {"full_system": true} instead of a list
    marks a system whose every bucket file is synced."""
    for s in systems:
        entry = games.get(s["bucket"], [])
        s["games"] = entry if isinstance(entry, list) else []
        s["full_system"] = isinstance(entry, dict) and bool(entry.get("full_system"))
    return systems


def apply_device_overlay(devices, systems, overlay):
    """Set each device's systems/note from the repo defaults, adjusted by the user's add/remove overlay.

    overlay: {device id: {"add": [system ids], "remove": [system ids]}}. Unknown ids warn and are skipped.
    """
    defaults = repo_json("device-systems")
    known = {s["bucket"] for s in systems}
    for d in devices:
        base = defaults.get(d["id"], {"systems": [], "note": ""})
        d["systems"], d["note"] = list(base["systems"]), base["note"]
    by_id = {d["id"]: d for d in devices}
    for dev_id, change in overlay.items():
        if dev_id not in by_id:
            print(f"warning: device-systems.json: unknown device {dev_id!r}, skipped", file=sys.stderr)
            continue
        if not isinstance(change, dict):
            continue
        for key in ("add", "remove"):
            for sid in change.get(key, []):
                if sid not in known:
                    print(f"warning: device-systems.json: {dev_id}: unknown system {sid!r}, skipped", file=sys.stderr)
        remove = set(change.get("remove", []))
        d = by_id[dev_id]
        d["systems"] = [x for x in d["systems"] if x not in remove]
        d["systems"] += [x for x in dict.fromkeys(change.get("add", [])) if x in known and x not in d["systems"]]


def load_manifest():
    """Systems, devices and layouts from the repo, joined with the personal games and device-system overlay."""
    seed_personal_files()
    manifest = {name: repo_json(name) for name in ("layouts", "systems", "devices")}
    apply_games(manifest["systems"], personal_json("games.json"))
    overlay_path = os.path.join(data_dir(), "device-systems.json")
    overlay = personal_json("device-systems.json") if os.path.exists(overlay_path) else {}
    apply_device_overlay(manifest["devices"], manifest["systems"], overlay)
    return manifest


def listed(s):
    """Bucket keys of the games games.json lists for a system."""
    return [g["bucket"] for g in s.get("games", []) if g.get("bucket")]


def available_keys(s, have):
    """Bucket keys to download: every file in the folder for full systems, else the game list.

    have: {key: size} listing of the system's bucket folder.
    """
    if s.get("full_system"):
        return sorted(k for k in have if not k.endswith("/"))
    return listed(s)


def local_sizes(root, prefix=""):
    """{key: size} of the files under root whose key starts with prefix (a folder, ending in /)."""
    out = {}
    for folder, _, files in os.walk(os.path.join(root, prefix)):
        for name in files:
            path = os.path.join(folder, name)
            out[os.path.relpath(path, root).replace(os.sep, "/")] = os.path.getsize(path)
    return out


def list_sizes(prefix):
    if _mirror_root:
        return local_sizes(_mirror_root, prefix)
    out = aws("s3api", "list-objects-v2", "--bucket", BUCKET, "--prefix", prefix,
              "--query", "Contents[].[Key,Size]", "--output", "json")
    return {k: s for k, s in (json.loads(out) or [])}


def pick_device(devices, cursor=0):
    """Returns a device dict, "full", or None on Esc."""
    options = [(f"📟 {d['name']}", d) for d in devices] + [("🌍 Full (every system)", "full")]
    i = filter_list("🎯 Which device?", [label for label, _ in options], cursor=cursor,
                    hint="type to filter · ↑/↓ move · Enter continue · Esc quit")
    return None if i is None else options[i][1]


def pick_layout(layouts, default):
    """Returns a layout name, or None on Esc. default: layout name the cursor starts on."""
    names = list(layouts)
    labels = [f"{l['label']}  ({l['roms_dir']}/ {l['bios_dir']}/)" for l in layouts.values()]
    i = filter_list("🗂️  Which folder layout?", labels, cursor=names.index(default) if default in names else 0,
                    hint="type to filter · ↑/↓ move · Enter continue · Esc back")
    return None if i is None else names[i]


def choose_setup(manifest):
    """Ask for the device, then the layout (Esc steps back). Returns (device dict or None for Full, layout name)."""
    devices, layouts = manifest["devices"], manifest["layouts"]
    device = None
    while True:
        choice = pick_device(devices)
        if choice is None:
            raise SystemExit(yellow("👋 Cancelled."))
        device = choice if isinstance(choice, dict) else None
        default = device["layout"] if device else next(iter(layouts))
        layout = pick_layout(layouts, default)
        if layout is not None:
            return device, layout


def pick_systems(rows, initial=None):
    """rows: list of (label, has_roms, need_bytes, total_bytes); initial: indexes toggled on at start. Returns selected indexes, or None if quit."""
    def run(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        on = off = head = 0
        if curses.has_colors():
            curses.start_color()
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_CYAN, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)
            on, head, off = curses.color_pair(1), curses.color_pair(2), curses.color_pair(3)
        sel = [i in (initial or ()) for i in range(len(rows))]
        show_empty = False
        cur = top = 0
        while True:
            # systems with ROMs first, then (when shown) the empty ones; stable within each group
            order = [i for i, r in enumerate(rows) if r[1]]
            if show_empty:
                order += [i for i, r in enumerate(rows) if not r[1]]
            cur = min(cur, len(order) - 1)
            stdscr.erase()
            h, w = stdscr.getmaxyx()
            hidden = len(rows) - len(order)
            stdscr.addnstr(0, 0, "🕹  Pick systems", w - 1, head | curses.A_BOLD)
            stdscr.addnstr(1, 0, "↑/↓ move · space/tab toggle · a all on · n all off · "
                           "e show/hide 0-ROM systems · enter go · q quit", w - 1, curses.A_DIM)
            view = h - 4
            if cur < top:
                top = cur
            elif cur >= top + view:
                top = cur - view + 1
            for pos in range(top, min(len(order), top + view)):
                i = order[pos]
                mark = "✅" if sel[i] else "⬜"
                attr = (on if sel[i] else 0) | (curses.A_REVERSE if pos == cur else 0)
                if not rows[i][1]:
                    attr |= curses.A_DIM
                stdscr.addnstr(pos - top + 2, 0, f"{mark} {rows[i][0]}", w - 1, attr)
            need = sum(r[2] for r, on_ in zip(rows, sel) if on_)
            total = sum(r[3] for r, on_ in zip(rows, sel) if on_)
            status = f"{sum(sel)} selected · {human_size(need)} to download ({human_size(total)} total)"
            if hidden:
                status += f" · {hidden} systems with 0 ROMs hidden (press e)"
            stdscr.addnstr(h - 1, 0, status, w - 1, off | curses.A_BOLD)
            k = stdscr.getch()
            if k in (curses.KEY_UP, ord("k")):
                cur = max(0, cur - 1)
            elif k in (curses.KEY_DOWN, ord("j")):
                cur = min(len(order) - 1, cur + 1)
            elif k == curses.KEY_PPAGE:
                cur = max(0, cur - view)
            elif k == curses.KEY_NPAGE:
                cur = min(len(order) - 1, cur + view)
            elif k in (ord(" "), 9) and order:
                sel[order[cur]] = not sel[order[cur]]
            elif k == ord("a"):
                for i in order:
                    sel[i] = True
            elif k == ord("n"):
                sel = [False] * len(rows)
            elif k == ord("e"):
                show_empty = not show_empty
            elif k in (10, 13, curses.KEY_ENTER):
                return [i for i, s in enumerate(sel) if s]
            elif k == ord("q"):
                return None
    return curses.wrapper(run)


def confirm(question, default=True):
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        a = input(f"{question} {suffix} ").strip().lower()
        if not a:
            return default
        if a in ("y", "yes"):
            return True
        if a in ("n", "no"):
            return False


def check_dir(path, label):
    """Fail early if `path` can't be used or created. Returns True if it must be created."""
    if os.path.exists(path):
        if not os.path.isdir(path):
            raise SystemExit(red(f"❌ {label} {path} exists but is not a directory"))
        if not os.access(path, os.W_OK | os.X_OK):
            raise SystemExit(red(f"❌ No write permission for {label} {path}"))
        return False
    parent = os.path.dirname(path)
    while not os.path.exists(parent):
        parent = os.path.dirname(parent)
    if not os.path.isdir(parent) or not os.access(parent, os.W_OK | os.X_OK):
        raise SystemExit(red(f"❌ Can't create {label} {path}: no write permission in {parent}"))
    return True


def prepare_dirs(base, layout, dry_run, ask=True):
    """Show, validate and (after confirmation, unless ask is False) create the layout's ROM and BIOS folders under base.

    Returns (roms, bios), or None if declined.
    """
    roms = os.path.join(base, layout["roms_dir"])
    bios = os.path.join(base, layout["bios_dir"])
    # check everything before asking anything
    missing = {path for label, path in (("ROMs folder", roms), ("BIOS folder", bios)) if check_dir(path, label)}
    print(bold(f"📁 {layout['label']} layout in {base}:"))
    for icon, name, path in (("💿", "ROMs", roms), ("🧠", "BIOS", bios)):
        print(f"  {icon} {name} → {cyan(path)}" + (dim("  (will be created)") if path in missing else ""))
    if ask and not confirm("Continue with these folders?"):
        return None
    for path in sorted(missing):
        if dry_run:
            print(yellow(f"🧪 Would create {path}"))
        else:
            os.makedirs(path)
    return roms, bios


def data_dir():
    """Per-user data folder for this script."""
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "sync-roms")
    xdg = os.environ.get("XDG_DATA_HOME")
    return os.path.join(xdg, "sync-roms") if xdg else os.path.expanduser("~/.sync-roms")


def load_cards():
    """Saved {root folder name: {"device": device id or "full", "layout": layout name, "android_media": "always" or "never"}}."""
    try:
        with open(os.path.join(data_dir(), "cards.json")) as f:
            cards = json.load(f)
    except (OSError, ValueError):
        return {}
    return cards if isinstance(cards, dict) else {}


def update_card(name, **values):
    """Merge values into a card's saved entry, keeping its other keys."""
    cards = load_cards()
    entry = cards.get(name)
    cards[name] = {**(entry if isinstance(entry, dict) else {}), **values}
    try:
        os.makedirs(data_dir(), exist_ok=True)
        with open(os.path.join(data_dir(), "cards.json"), "w") as f:
            json.dump(cards, f, indent=2, sort_keys=True)
    except OSError as e:
        print(yellow(f"  ⚠️  Couldn't remember this setting: {e}"))


def save_card(name, device, layout):
    update_card(name, device=device["id"] if device else "full", layout=layout)


def filter_list(title, labels, multi=False, initial=None, hint="", cursor=0):
    """Type-to-filter list. Every space-separated term must appear in a label (case-insensitive).

    Single mode returns the chosen index. Multi mode (Tab toggles) returns the list of
    on/off states. Both return None on Esc. cursor: index the highlight starts on.
    """
    os.environ.setdefault("ESCDELAY", "25")
    lowered = [l.lower() for l in labels]
    start = list(initial) if initial is not None else [False] * len(labels)

    def run(stdscr):
        curses.curs_set(1)
        curses.use_default_colors()
        green_a = red_a = cyan_a = 0
        if curses.has_colors():
            curses.start_color()
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_RED, -1)
            curses.init_pair(3, curses.COLOR_CYAN, -1)
            green_a, red_a, cyan_a = (curses.color_pair(n) for n in (1, 2, 3))
        state = list(start)
        query = ""
        vis = list(range(len(labels)))
        cur, top = cursor, 0
        while True:
            terms = query.lower().split()
            vis = [i for i, l in enumerate(lowered) if all(t in l for t in terms)]
            cur = max(0, min(cur, len(vis) - 1))
            h, w = stdscr.getmaxyx()
            view = max(1, h - 4)
            if cur < top:
                top = cur
            elif cur >= top + view:
                top = cur - view + 1
            stdscr.erase()
            stdscr.addnstr(0, 0, title, w - 1, cyan_a | curses.A_BOLD)
            stdscr.addnstr(1, 0, "🔎 " + query, w - 1)
            keys = ("↑/↓ move · Tab toggle · ^A toggle all shown · Enter done · Esc cancel"
                    if multi else "↑/↓ move · Enter select · Esc finish")
            stdscr.addnstr(2, 0, hint or keys, w - 1, curses.A_DIM)
            for pos in range(top, min(len(vis), top + view)):
                i = vis[pos]
                attr = curses.A_REVERSE if pos == cur else 0
                if multi:
                    if state[i] == start[i]:
                        mark = "✅" if state[i] else "⬜"
                    else:
                        mark = "➕" if state[i] else "➖"
                        attr |= green_a if state[i] else red_a
                    line = f"{mark} {labels[i]}"
                else:
                    line = labels[i]
                stdscr.addnstr(pos - top + 3, 0, line, w - 1, attr)
            added = sum(1 for a, b in zip(state, start) if a and not b)
            removed = sum(1 for a, b in zip(state, start) if b and not a)
            status = f"{len(vis)}/{len(labels)} shown"
            if multi:
                status += f" · +{added} −{removed} pending"
            stdscr.addnstr(h - 1, 0, status, w - 1, curses.A_BOLD)
            stdscr.move(1, min(w - 1, 3 + len(query)))
            try:
                k = stdscr.get_wch()
            except curses.error:
                continue
            if k == curses.KEY_UP:
                cur = max(0, cur - 1)
            elif k == curses.KEY_DOWN:
                cur = min(len(vis) - 1, cur + 1)
            elif k == curses.KEY_PPAGE:
                cur = max(0, cur - view)
            elif k == curses.KEY_NPAGE:
                cur = min(len(vis) - 1, cur + view)
            elif k in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                query = query[:-1]
                cur = top = 0
            elif k == "\x15":  # ^U clears the filter
                query = ""
                cur = top = 0
            elif k == "\x1b":
                return None
            elif k in ("\n", "\r", curses.KEY_ENTER):
                if multi:
                    return state
                if vis:
                    return vis[cur]
            elif k == "\t" and multi and vis:
                state[vis[cur]] = not state[vis[cur]]
            elif k == "\x01" and multi and vis:
                target = not all(state[i] for i in vis)
                for i in vis:
                    state[i] = target
            elif isinstance(k, str) and k.isprintable():
                query += k
                cur = top = 0
    return curses.wrapper(run)


def snapshot(data):
    return {s["bucket"]: {g["bucket"] for g in s.get("games", []) if g.get("bucket")}
            for s in data["systems"]}


def edit_manifest():
    """Add/remove games in the local games.json (browsing what's in the bucket), then save it."""
    print(bold("✏️  Edit mode") + dim(f"  read={PROFILE}"))
    seed_personal_files()
    path = os.path.join(data_dir(), "games.json")
    games = personal_json("games.json")
    data = {"systems": apply_games(repo_json("systems"), games)}
    original = snapshot(data)
    systems = sorted(data["systems"], key=lambda s: s["name"].lower())

    while True:
        now = snapshot(data)
        labels = []
        for s in systems:
            changed = now[s["bucket"]] ^ original[s["bucket"]]
            pending = f"  ✏️ {len(changed)} change(s)" if changed else ""
            count = "full system" if s.get("full_system") else f"{len(now[s['bucket']])} games"
            labels.append(f"{s['name']}  ({count}){pending}")
        i = filter_list("✏️  Pick a system to edit (Esc = finish)", labels)
        if i is None:
            break
        s = systems[i]
        if s.get("full_system"):
            print(yellow(f"ℹ️  {s['name']} is a full system: every file in its bucket folder is "
                         "downloaded, so there is no game list to edit."))
            continue
        print(dim(f"📡 Listing s3://{BUCKET}/{s['bucket']}/ ..."))
        in_bucket = {k for k in list_sizes(s["bucket"] + "/") if not k.endswith("/")}
        listed = {g["bucket"] for g in s["games"] if g.get("bucket")}
        keys = sorted(in_bucket | listed, key=str.lower)
        labels = [k.split("/", 1)[1] + ("" if k in in_bucket else "  ⚠️ not in bucket") for k in keys]
        state = filter_list(f"✏️  {s['name']} — ✅ in games.json, ⬜ in bucket only",
                            labels, multi=True, initial=[k in listed for k in keys])
        if state is None:
            continue
        for key, on in zip(keys, state):
            if on and key not in listed:
                name = key.split("/", 1)[1]
                s["games"].append({"file": name, "title": os.path.splitext(name)[0],
                                   "bucket": key})
            elif not on and key in listed:
                s["games"] = [g for g in s["games"] if g.get("bucket") != key]
        listed = None

    now = snapshot(data)
    added = {e: sorted(now[e] - original[e]) for e in now if now[e] - original[e]}
    removed = {e: sorted(original[e] - now[e]) for e in now if original[e] - now[e]}
    if not added and not removed:
        print(yellow("👋 No changes, nothing saved."))
        return 0
    print(bold("\n📝 Changes"))
    for label, group, sign, col in (("Added", added, "➕", green), ("Removed", removed, "➖", red)):
        for esde, ks in group.items():
            print(col(f"  {sign} {esde}: {len(ks)} {label.lower()}"))
            for k in ks[:MAX_MISSING_SHOWN]:
                print(dim(f"       {k.split('/', 1)[1]}"))
            if len(ks) > MAX_MISSING_SHOWN:
                print(dim(f"       … and {len(ks) - MAX_MISSING_SHOWN} more"))
    print(dim("  (Removing only drops a game from games.json; the file stays in the bucket.)"))

    if not confirm(f"💾 Save games.json to {path}?"):
        print(yellow("👋 Not saved."))
        return 0
    with open(path + ".tmp", "w") as f:
        json.dump({s["bucket"]: {"full_system": True} if s["full_system"] else s["games"]
                   for s in data["systems"] if s["full_system"] or s["games"]}, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(path + ".tmp", path)
    print(green("🎉 Saved games.json"))
    return 0


def plan_downloads(jobs):
    """jobs: list of (s3_key, local_path, expected_size). Drops files already present."""
    return [(k, p, s) for k, p, s in jobs
            if not (s is not None and os.path.exists(p) and os.path.getsize(p) == s)]


_s3 = {}


def s3_client(profile=None):
    """Shared boto3 S3 client for a profile, or None if boto3 or the profile isn't usable (use the aws CLI)."""
    profile = profile or PROFILE
    if profile not in _s3:
        try:
            _s3[profile] = boto3.Session(profile_name=profile).client(
                "s3", config=Config(max_pool_connections=WORKERS)) if boto3 else False
        except Exception:
            _s3[profile] = False
    return _s3[profile] or None


def download(job):
    key, path, _ = job
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if _mirror_root:
        shutil.copyfile(os.path.join(_mirror_root, key), path + ".part")
        os.replace(path + ".part", path)
        return
    client = s3_client()
    if client:
        client.download_file(BUCKET, key, path)
    else:
        aws("s3", "cp", f"s3://{BUCKET}/{key}", path, "--only-show-errors")


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def run_downloads(todo, label, icon, base):
    if not todo:
        print(green(f"{icon} {label}: nothing to download ✨"))
        return 0
    print(bold(f"\n{icon} {label}: downloading {len(todo)} file(s)"))
    failed = 0
    ex = ThreadPoolExecutor(WORKERS)
    try:
        futs = [(j, ex.submit(download, j)) for j in todo]
        for i, (j, f) in enumerate(futs, 1):
            prog = dim(f"[{i}/{len(todo)}]")
            try:
                f.result()
                src = j[0].split("/", 1)[0]
                rel = os.path.relpath(j[1], base)
                shown = j[0] if rel.split(os.sep, 1)[0] == src else f"{src} → {rel}"
                print(f"  {prog} ✅ {shown}")
            except Exception as e:
                failed += 1
                print(f"  {prog} ❌ {red(j[0])}: {(getattr(e, 'stderr', None) or str(e)).strip()}")
    except KeyboardInterrupt:
        print(yellow("\n🛑 Interrupted — dropping queued downloads, finishing the ones in flight..."))
        raise
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
    return failed


# Files/folders that frontends put in a system's ROM folder. They aren't ROMs, so they never
# count as "files present" and are never offered for deletion (dotfiles are ignored too).
IGNORED_ROOT_FILES = {
    "systeminfo.txt", "systems.txt", "noload.txt", "flatten.txt",  # ES-DE
    "_info.txt", "gamelist.xml",                                   # Batocera / Knulli
    "miyoogamelist.xml",                                           # Onion
}
IGNORED_ROOT_DIRS = {"images", "videos", "manuals",                # Batocera / Knulli scraped media
                     "imgs"}                                       # Onion scraped box art
IGNORED_FILES = {"thumbs.db", "desktop.ini"}                       # Windows


def walk_roms(dest):
    """os.walk over dest that yields only real ROM-folder content (no frontend/OS leftovers)."""
    for root, dirs, files in os.walk(dest):
        at_root = os.path.normpath(root) == os.path.normpath(dest)
        dirs[:] = [d for d in dirs
                   if not d.startswith(".") and not (at_root and d.lower() in IGNORED_ROOT_DIRS)]
        files = [f for f in files
                 if not f.startswith(".") and f.lower() not in IGNORED_FILES
                 and not (at_root and f.lower() in IGNORED_ROOT_FILES)]
        yield root, files


def has_local_files(dest):
    """True if dest has any ROM file (frontend files and dotfiles are ignored)."""
    return any(files for _, files in walk_roms(dest))


def find_extras(dest, wanted_keys):
    """Local files under dest that aren't in the system's ROM list (frontend files and dotfiles are ignored)."""
    expected = {os.path.normpath(k.split("/", 1)[1]) for k in wanted_keys}
    extras = []
    for root, files in walk_roms(dest):
        for f in files:
            path = os.path.join(root, f)
            if os.path.normpath(os.path.relpath(path, dest)) not in expected:
                extras.append(path)
    return extras


def report_missing(keys, what):
    if not keys:
        return
    print(yellow(f"  ⚠️  {len(keys)} {what} listed in manifest but not in bucket"))
    for k in keys[:MAX_MISSING_SHOWN]:
        print(dim(f"       {k}"))
    if len(keys) > MAX_MISSING_SHOWN:
        print(dim(f"       … and {len(keys) - MAX_MISSING_SHOWN} more"))


_clean_root = None


def dot_clean(path):
    """Run dot_clean -m on path, which should delete every ._* file. Returns (exit ok, ._* files still there)."""
    r = subprocess.run(["dot_clean", "-m", path], capture_output=True, text=True)
    # dot_clean exits 0 even when a merge fails, so also look for ._* files it left behind
    left = [os.path.join(root, f) for root, _, files in os.walk(path) for f in files if f.startswith("._")]
    ok = r.returncode == 0 and not left
    print(f"  {'✅' if ok else '❌'} {path}"
          + (dim(f" ({len(left)} ._ file(s) left)") if left else "")
          + ("" if r.returncode == 0 else red(f": {r.stderr.strip()}")))
    return r.returncode == 0, left


ANDROID_MEDIA_DIRS = ("Alarms", "Audiobooks", "DCIM", "Documents", "Download", "Movies", "Music",
                      "Notifications", "Pictures", "Podcasts", "Recordings", "Ringtones")


def android_media_files(base):
    """{folder: files} for the Android media folders that exist in base (files other than .nomedia)."""
    found = {}
    for name in ANDROID_MEDIA_DIRS:
        folder = os.path.join(base, name)
        if os.path.isdir(folder):
            found[name] = [os.path.join(root, f) for root, _, files in os.walk(folder) for f in files if f != ".nomedia"]
    return found


def clean_android_media(base, card, dry_run, ask=False):
    """Empty the Android media folders on the card and put a .nomedia in each, as the card's saved setting says.

    The setting (android_media in cards.json) is "always" or "never" and is used without asking. Without
    one, ask when any of the folders has files, and remember the answer. Folders that don't exist are not
    created. With ask, the saved setting is confirmed first; declining it asks the question again and
    saves the new answer.
    """
    found = android_media_files(base)
    files = [f for fs in found.values() for f in fs]
    setting = (load_cards().get(card) or {}).get("android_media")
    redo = False
    if ask and not dry_run and setting in ("always", "never"):
        what = "remove the files in the Android media folders and add .nomedia" if setting == "always" else "leave the Android media folders alone"
        if not confirm(f"Use the saved setting for {card}: {what}?"):
            setting, redo = None, True
    if not redo and (not found or setting == "never" or (setting != "always" and not files)):
        return
    counts = ", ".join(f"{name} ({len(fs)})" for name, fs in found.items() if fs)
    if dry_run:
        print(f"📵 Android media folders: {len(files)} file(s) would be removed and .nomedia added "
              f"({'setting: always' if setting == 'always' else 'would ask first'}){': ' + counts if counts else ''}")
        return
    if setting != "always":
        size = sum(os.path.getsize(f) for f in files if os.path.exists(f))
        print(bold(f"\n📵 Android media folders on {card} have {len(files)} file(s) ({human_size(size)})"
                   + (f": {counts}" if counts else "")))
        answer = confirm("Remove them and add a .nomedia file to each folder? Your answer is remembered for this card name.",
                         default=False)
        update_card(card, android_media="always" if answer else "never")
        if not answer:
            print(yellow("  ↩️  Keeping them (not asking again for this card)"))
            return
    removed = 0
    for path in files:
        try:
            os.remove(path)
            removed += 1
        except OSError as e:
            print(red(f"  ❌ {path}: {e}"))
    for name in found:
        try:
            open(os.path.join(base, name, ".nomedia"), "a").close()
        except OSError as e:
            print(red(f"  ❌ {name}/.nomedia: {e}"))
    print(green(f"📵 Removed {removed} file(s) from the Android media folders and added .nomedia to {len(found)} folder(s)"))


def quiet_fseventsd(root):
    """Empty the root's .fseventsd folder (macOS's file event log) and add .fseventsd/no_log so it isn't written again."""
    log_dir = os.path.join(root, ".fseventsd")
    try:
        os.makedirs(log_dir, exist_ok=True)
        for name in os.listdir(log_dir):
            path = os.path.join(log_dir, name)
            if name != "no_log" and os.path.isfile(path):
                os.remove(path)
        open(os.path.join(log_dir, "no_log"), "a").close()
    except OSError as e:
        print(yellow(f"  ⚠️  Couldn't clean .fseventsd in {root}: {e}"))


def clean_dirs():
    """Mark the root folder as not to be indexed, then merge/remove macOS AppleDouble (._*) files under it (macOS only)."""
    if not _clean_root:
        return
    try:  # on any OS: it keeps Spotlight from indexing the card when it is next used on a Mac
        open(os.path.join(_clean_root, ".metadata_never_index"), "a").close()
    except OSError as e:
        print(yellow(f"  ⚠️  Couldn't create .metadata_never_index in {_clean_root}: {e}"))
    quiet_fseventsd(_clean_root)
    if not shutil.which("dot_clean"):
        return
    print(bold("\n🧼 Running dot_clean..."))
    ok, left = dot_clean(_clean_root)
    if not ok or left:
        print(bold(f"\n🔍 dot_clean couldn't clean everything, turning Spotlight indexing off for {_clean_root} (sudo may ask for your password)..."))
        # sudo needs ^C to work at its password prompt, but main() ignores SIGINT for dot_clean
        default_sigint = lambda: signal.signal(signal.SIGINT, signal.SIG_DFL)
        for args in (["-i", "off"], ["-X"]):
            r = subprocess.run(["sudo", "mdutil", *args, _clean_root], preexec_fn=default_sigint)
            if r.returncode != 0:
                print(red(f"  ❌ sudo mdutil {' '.join(args)} failed ({r.returncode})"))
        print(bold("\n🧼 Retrying dot_clean..."))
        _, left = dot_clean(_clean_root)
    if left:
        print(red(f"\n⚠️  {len(left)} ._ file(s) are still there after dot_clean:"))
        for path in left[:10]:
            print(dim(f"     {path}"))
        if len(left) > 10:
            print(dim(f"     … and {len(left) - 10} more"))


# --- Scraped data (media, metadata, themes, collections, settings) --------------------------------
# Lives in the bucket under scrapes/. Metadata is neutral JSON with only the fields that are safe
# to share; media keeps ES-DE's media type folder names.
SCRAPES = "scrapes"
MEDIA_TYPES = {"3dboxes", "backcovers", "covers", "custom", "fanart", "manuals", "marquees",
               "miximages", "physicalmedia", "screenshots", "titlescreens", "videos"}
# Onion's box art is made at upload time (PNG, at most 250x360) from the first of ONION_ART found locally
# and stored as scrapes/<system>/onion/<ROM name>.png, so a sync only downloads it.
ONION_TYPE = "onion"
ONION_ART = ("covers", "3dboxes", "screenshots")
ONION_MAX = (250, 360)
BUCKET_MEDIA = MEDIA_TYPES | {ONION_TYPE}
TEXT_FIELDS = ("name", "desc", "developer", "publisher", "genre", "players")
UNKNOWN_FIELDS = {"developer", "publisher", "genre", "players"}  # ES-DE writes "unknown" for these
SETTING_PREFIXES = ("Scrape", "Miximage", "Theme")  # Scrape covers Scrape* and Scraper*
SETTING_EXCLUDE = {"ScraperUsernameScreenScraper", "ScraperPasswordScreenScraper",
                   "ScraperUseAccountScreenScraper", "ThemeAspectRatio"}
SETTING_UI = {"DefaultSortOrder", "FavoritesFirst", "FavoritesStar", "FavoritesAddButton",
              "FavStarCustom", "FavFirstCustom", "FoldersOnTop", "GamelistFilters", "ShowHiddenFiles",
              "ShowHiddenGames", "SaveGamelistsMode", "AlternativeEmulatorPerGame", "StartupView",
              "QuickSystemSelect", "RandomEntryButton", "ListScrollOverlay", "MAMENameStripExtraInfo",
              "CollectionCustomGrouping", "SystemsSorting"}
SETTING_LINE = re.compile(r'<(bool|int|string)\s+name="([^"]+)"\s+value="([^"]*)"\s*/>')


def dump_json(data):
    return json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def parse_gamelist(text):
    """{ROM path: safe fields} from an ES-DE gamelist.xml. Raises ET.ParseError if it is malformed.

    Only the <gameList> block is read: ES-DE can write an <alternativeEmulator> element before it,
    which leaves two top-level elements. Only the scraped fields are kept (no favorites, play
    counts, emulator choices or media tags), and values ES-DE writes for "nothing" are dropped.
    """
    m = re.search(r"<gameList\b.*</gameList>", text, re.S)
    games = {}
    if not m:
        return games
    for g in ET.fromstring(m.group(0)).findall("game"):
        path = (g.findtext("path") or "").strip()
        if not path.startswith("./"):
            continue
        fields = {}
        for f in TEXT_FIELDS:
            v = (g.findtext(f) or "").strip()
            if v and not (f in UNKNOWN_FIELDS and v.lower() == "unknown"):
                fields[f] = v
        try:
            rating = round(float(g.findtext("rating") or 0), 2)
        except ValueError:
            rating = 0
        if rating > 0:
            fields["rating"] = rating
        d = (g.findtext("releasedate") or "").strip()
        if re.match(r"\d{8}T", d) and not d.startswith("1970"):
            fields["releasedate"] = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        games[path[2:]] = fields
    return games


def merge_metadata(remote, local):
    """Local values replace the bucket's; entries (and fields) only in the bucket are kept."""
    merged = {k: dict(v) for k, v in remote.items()}
    for rom, fields in local.items():
        merged[rom] = {**merged.get(rom, {}), **fields}
    return merged


def merge_lines(remote, local):
    """Union of the lines of two text files: remote lines first, then new local ones."""
    seen, out = set(), []
    for line in (remote + "\n" + local).splitlines():
        line = line.strip()
        if line and line not in seen:
            seen.add(line)
            out.append(line)
    return "\n".join(out) + "\n" if out else ""


def share_setting(name):
    if re.search(r"password|username|passkey", name, re.I) or name in SETTING_EXCLUDE:
        return False
    return name.startswith(SETTING_PREFIXES) or name in SETTING_UI


def safe_settings(text):
    """{name: typed value} for the ES-DE settings that are safe to share, from es_settings.xml."""
    out = {}
    for kind, name, value in SETTING_LINE.findall(text):
        if not share_setting(name):
            continue
        value = unescape(value, {"&quot;": '"', "&apos;": "'"})
        try:
            out[name] = (value == "true") if kind == "bool" else int(value) if kind == "int" else value
        except ValueError:
            pass
    return out


def bucket_roms(systems, all_files=False):
    """{bucket folder: set of ROM paths in it}, from the bucket's real contents.

    By default only the ROMs a sync would install (the games games.json lists, or every file of a
    full system). With all_files, every file in the system's bucket folder.
    """
    todo = systems if all_files else [s for s in systems if s.get("full_system") or listed(s)]
    with ThreadPoolExecutor(WORKERS) as ex:
        listings = list(ex.map(lambda s: list_sizes(s["bucket"] + "/"), todo))
    roms = {s["bucket"]: set() for s in systems}
    for s, have in zip(todo, listings):
        keys = (k for k in have if not k.endswith("/")) if all_files else (k for k in available_keys(s, have) if k in have)
        roms[s["bucket"]] = {k.split("/", 1)[1] for k in keys}
    return roms


def rom_stems(roms):
    """{system: ROM paths without their extension}, which is how scraped media is named."""
    return {system: {os.path.splitext(r)[0] for r in paths} for system, paths in roms.items()}


def get_text(key):
    if _mirror_root:
        with open(os.path.join(_mirror_root, key), encoding="utf-8") as f:
            return f.read()
    return aws("s3", "cp", f"s3://{BUCKET}/{key}", "-")


def fetch_texts(keys):
    keys = sorted(keys)
    with ThreadPoolExecutor(WORKERS) as ex:
        return dict(zip(keys, ex.map(get_text, keys)))


def put_text(key, text):
    client = s3_client(WRITE_PROFILE)
    if client:
        client.put_object(Bucket=BUCKET, Key=key, Body=text.encode("utf-8"))
    else:
        subprocess.run(["aws", "--profile", WRITE_PROFILE, "s3", "cp", "-", f"s3://{BUCKET}/{key}",
                        "--only-show-errors"], input=text.encode("utf-8"), check=True, capture_output=True)


def put_file(key, path):
    client = s3_client(WRITE_PROFILE)
    if client:
        client.upload_file(path, BUCKET, key, ExtraArgs={
            "ContentType": mimetypes.guess_type(path)[0] or "application/octet-stream"})
    else:
        aws("s3", "cp", path, f"s3://{BUCKET}/{key}", "--only-show-errors", profile=WRITE_PROFILE)


def upload(job):
    key, path, _, *derive = job  # an optional 4th element means: upload path shrunk to Onion's box art size
    if not derive:
        return put_file(key, path)
    with tempfile.TemporaryDirectory() as tmp:
        art = os.path.join(tmp, "art.png")
        shrink_png(path, art)
        put_file(key, art)


def walk_files(root, skip_top=()):
    """(relative path with /, full path) of every non-hidden file under root."""
    for dp, dns, fns in os.walk(root):
        at_root = os.path.normpath(dp) == os.path.normpath(root)
        dns[:] = sorted(d for d in dns if not d.startswith(".") and not (at_root and d in skip_top))
        for f in sorted(fns):
            if not f.startswith("."):
                full = os.path.join(dp, f)
                yield os.path.relpath(full, root).replace(os.sep, "/"), full


def plan_upload(es_dir, roms, existing, remote_texts):
    """What to upload from an ES-DE data folder.

    roms: {system: available ROM paths}; existing: {key: size} under scrapes/;
    remote_texts: {key: text} of the bucket's text files. Returns a dict with
    files [(key, path, size)], texts [(key, text, label)], present (files already in the bucket),
    derived [(key, source path, source size, "onion")] (Onion box art the bucket doesn't have yet,
    made from the local image even when that image itself was already uploaded), derived_present
    and warnings.
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
            local = parse_gamelist(read(path))
        except (ET.ParseError, OSError, UnicodeDecodeError) as e:
            plan["warnings"].append(f"{system}: couldn't read gamelist.xml ({e}), skipped")
            continue
        local = {k: v for k, v in local.items() if k in roms[system] and v}
        key = f"{SCRAPES}/{system}/metadata.json"
        old = remote_texts.get(key, "")
        try:
            remote = json.loads(old) if old else {}
        except ValueError:
            plan["warnings"].append(f"{key} in the bucket isn't valid JSON, skipped")
            continue
        merged = merge_metadata(remote, local)
        if local and dump_json(merged) != old:
            new = len(set(merged) - set(remote))
            plan["texts"].append((key, dump_json(merged), f"{system} metadata (+{new} new, {len(local) - new} checked)"))

    media = os.path.join(es_dir, "downloaded_media")
    art = defaultdict(dict)  # (system, ROM name) -> {media type: local path} for Onion box art
    for system in sorted(os.listdir(media)) if os.path.isdir(media) else []:
        if not stems.get(system):
            continue
        for mtype in sorted(MEDIA_TYPES):
            base = os.path.join(media, system, mtype)
            for rel, full in walk_files(base) if os.path.isdir(base) else []:
                stem = os.path.splitext(rel)[0]
                if stem in stems[system]:
                    want_file(f"{SCRAPES}/{system}/{mtype}/{rel}", full)
                    if mtype in ONION_ART and "/" not in stem:  # Onion's Imgs folder is flat
                        art[(system, stem)][mtype] = full
    for (system, stem), found in sorted(art.items()):
        key = f"{SCRAPES}/{system}/{ONION_TYPE}/{stem}.png"
        if key in existing:
            plan["derived_present"] += 1
        else:
            source = found[next(t for t in ONION_ART if t in found)]
            plan["derived"].append((key, source, os.path.getsize(source), ONION_TYPE))

    themes = os.path.join(es_dir, "themes")
    for rel, full in walk_files(themes, skip_top=("themes-list",)) if os.path.isdir(themes) else []:
        want_file(f"{SCRAPES}/esde/themes/{rel}", full)

    collections = os.path.join(es_dir, "collections")
    for name in sorted(os.listdir(collections)) if os.path.isdir(collections) else []:
        if name.endswith(".cfg") and not name.startswith("."):
            key = f"{SCRAPES}/esde/collections/{name}"
            old = remote_texts.get(key, "")
            new = merge_lines(old, read(os.path.join(collections, name)))
            if new and new != old:
                plan["texts"].append((key, new, f"collection {name}"))

    settings = os.path.join(es_dir, "settings", "es_settings.xml")
    if os.path.isfile(settings):
        local = safe_settings(read(settings))
        key = f"{SCRAPES}/esde/settings.json"
        old = remote_texts.get(key, "")
        try:
            remote = json.loads(old) if old else {}
        except ValueError:
            plan["warnings"].append(f"{key} in the bucket isn't valid JSON, skipped")
            remote = None
        if remote is not None and local and dump_json({**remote, **local}) != old:
            plan["texts"].append((key, dump_json({**remote, **local}), f"settings (+{len(set(local) - set(remote))} new)"))
    return plan


def text_keys(existing):
    """Keys under scrapes/ that are text files we merge into."""
    return [k for k in existing if k.endswith("/metadata.json") or "/esde/collections/" in k
            or k == f"{SCRAPES}/esde/settings.json"]


def run_uploads(todo):
    print(bold(f"\n☁️  Uploading {len(todo)} file(s)"))
    failed = 0
    ex = ThreadPoolExecutor(WORKERS)
    try:
        futs = [(j, ex.submit(upload, j)) for j in todo]
        for i, (j, f) in enumerate(futs, 1):
            prog = dim(f"[{i}/{len(todo)}]")
            try:
                f.result()
                print(f"  {prog} ✅ {j[0]}")
            except Exception as e:
                failed += 1
                print(f"  {prog} ❌ {red(j[0])}: {(getattr(e, 'stderr', None) or str(e)).strip()}")
    except KeyboardInterrupt:
        print(yellow("\n🛑 Interrupted — dropping queued uploads, finishing the ones in flight..."))
        raise
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
    return failed


def upload_scrapes(args):
    """Upload BASE_DIR/ES-DE scraped data to the bucket's scrapes/ folder, merging with what's there."""
    base = os.path.abspath(os.path.expanduser(args.base_dir or os.getcwd()))
    es_dir = os.path.join(base, "ES-DE")
    if not os.path.isdir(es_dir):
        raise SystemExit(red(f"❌ No ES-DE folder in {base}"))
    saved = load_cards().get(os.path.basename(base) or base)
    if isinstance(saved, dict) and saved.get("layout") not in (None, "esde"):
        raise SystemExit(red(f"❌ {base} is set up as a {saved['layout']} card; scraped data is only uploaded from the esde layout"))

    print(bold("☁️  Upload scrapes") + dim(f"  read={PROFILE}  write={WRITE_PROFILE}  from {es_dir}"))
    try:
        manifest = load_manifest()
        print("📏 Listing the ROMs available in the bucket...")
        roms = bucket_roms(manifest["systems"])
        print("☁️  Listing what's already in scrapes/...")
        existing = list_sizes(SCRAPES + "/")
        remote_texts = fetch_texts(text_keys(existing))
        print("🔎 Comparing...")
        plan = plan_upload(es_dir, roms, existing, remote_texts)
    except subprocess.CalledProcessError as e:
        raise SystemExit(red(f"❌ {e.stderr.strip()}"))
    for w in plan["warnings"]:
        print(yellow(f"  ⚠️  {w}"))
    files, texts, derived = plan["files"], plan["texts"], plan["derived"]
    if derived and not can_shrink():
        print(yellow(f"  ⚠️  Onion box art needs Pillow or macOS sips to resize images; skipping {len(derived)} file(s)"))
        derived = []
    print(f"\n📝 Text files to write: {bold(str(len(texts)))}")
    for _, _, label in texts[:15]:
        print(dim(f"     {label}"))
    if len(texts) > 15:
        print(dim(f"     … and {len(texts) - 15} more"))
    print(f"🖼️  Files to upload (media, themes): {bold(str(len(files)))} "
          f"({human_size(sum(f[2] for f in files))}), {plan['present']} already there")
    print(f"🧅 Onion box art to create from local images: {bold(str(len(derived)))}, {plan['derived_present']} already there")
    if not files and not texts and not derived:
        print(green("Nothing to upload ✨"))
        return 0
    if args.dry_run:
        print(yellow("\n🧪 Dry run — nothing uploaded"))
        for key, _, size, *_ in (files + derived)[:20]:
            print(f"  {key} {dim(human_size(size))}")
        if len(files) + len(derived) > 20:
            print(dim(f"  … and {len(files) + len(derived) - 20} more"))
        return 0
    if not confirm(f"☁️  Upload to s3://{BUCKET}/{SCRAPES}/ ?", default=False):
        print(yellow("👋 Cancelled."))
        return 0
    failed = 0
    for key, text, label in texts:
        try:
            put_text(key, text)
            print(f"  ✅ {label}")
        except Exception as e:
            failed += 1
            print(f"  ❌ {red(label)}: {(getattr(e, 'stderr', None) or str(e)).strip()}")
    failed += run_uploads(files + derived) if files or derived else 0
    print(green("\n🎉 Done!") if not failed else red(f"\n⚠️  Done with {failed} failure(s)"))
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
        if len(parts) < 3 or parts[0] != SCRAPES or parts[1] == "esde" or key.endswith("/"):
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
                rewrites.append((key, dump_json(keep)))
            else:
                delete.append(key)
        elif parts[2] in BUCKET_MEDIA and len(parts) > 3:
            if os.path.splitext("/".join(parts[3:]))[0] not in stems.get(system, ()):
                delete.append(key)
                per[system]["media"] += 1
                per[system]["bytes"] += size
    return delete, rewrites, per, warnings


def delete_keys(keys):
    """Delete bucket objects in batches of 1000. Returns the errors S3 reported."""
    errors = []
    for i in range(0, len(keys), 1000):
        batch = keys[i:i + 1000]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"Objects": [{"Key": k} for k in batch], "Quiet": True}, f)
        try:
            out = aws("s3api", "delete-objects", "--bucket", BUCKET, "--delete", f"file://{f.name}",
                      "--output", "json", profile=WRITE_PROFILE)
            errors += (json.loads(out) if out.strip() else {}).get("Errors", [])
        finally:
            os.unlink(f.name)
        print(dim(f"  deleted {min(i + 1000, len(keys))}/{len(keys)}"))
    return errors


def clean_scrapes(args):
    """Remove scrapes/ media and metadata for ROMs that aren't in the bucket (any ROM file, listed in games.json or not)."""
    print(bold("🧹 Clean scrapes") + dim(f"  read={PROFILE}  write={WRITE_PROFILE}"))
    try:
        manifest = load_manifest()
        print("📏 Listing every ROM in the bucket...")
        roms = bucket_roms(manifest["systems"], all_files=True)
        print("☁️  Listing scrapes/...")
        existing = list_sizes(SCRAPES + "/")
        remote_texts = fetch_texts([k for k in text_keys(existing) if k.endswith("/metadata.json")])
    except subprocess.CalledProcessError as e:
        raise SystemExit(red(f"❌ {e.stderr.strip()}"))
    delete, rewrites, per, warnings = plan_clean(existing, roms, remote_texts)
    for w in warnings:
        print(yellow(f"  ⚠️  {w}"))
    if not delete and not rewrites:
        print(green("Nothing to clean ✨"))
        return 0
    print(bold("\nFor ROMs that aren't in the bucket:"))
    for system in sorted(per):
        c = per[system]
        print(f"  {system}: {c['media']} media file(s) ({human_size(c['bytes'])}), {c['entries']} metadata entr{'y' if c['entries'] == 1 else 'ies'}")
    for key in delete[:10]:
        print(dim(f"     {key}"))
    if len(delete) > 10:
        print(dim(f"     … and {len(delete) - 10} more"))
    if args.dry_run:
        print(yellow("\n🧪 Dry run — nothing deleted"))
        return 0
    if not confirm(f"🗑️  Permanently delete {len(delete)} object(s) and rewrite {len(rewrites)} metadata file(s)?", default=False):
        print(yellow("↩️  Keeping everything"))
        return 0
    failed = 0
    try:
        for key, text in rewrites:
            put_text(key, text)
        failed = len(delete_keys(delete)) if delete else 0
    except subprocess.CalledProcessError as e:
        raise SystemExit(red(f"❌ {e.stderr.strip()}"))
    print(green("\n🎉 Done!") if not failed else red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0


# --- Installing scraped data ------------------------------------------------------------------------
# A sync places the bucket's scrapes/ data for the chosen systems on the card, converted for the layout:
# esde keeps ES-DE's media folders and gamelists, knulli gets images/videos/manuals and a gamelist.xml
# with explicit media tags, onion gets the box art made for it at upload time in Imgs/ and a miyoogamelist.xml.
# Knulli: (gamelist tag, folder, file suffix, ES-DE media types to take it from; first one found wins)
KNULLI_MEDIA = (
    ("image", "images", "image", ("miximages", "screenshots")),
    ("thumbnail", "images", "thumb", ("covers",)),
    ("marquee", "images", "marquee", ("marquees",)),
    ("fanart", "images", "fanart", ("fanart",)),
    ("boxback", "images", "boxback", ("backcovers",)),
    ("titleshot", "images", "titleshot", ("titlescreens",)),
    ("video", "videos", "video", ("videos",)),
    ("manual", "manuals", "manual", ("manuals",)),
)
KNULLI_SUFFIXES = {"image", "thumb", "marquee", "fanart", "boxback", "titleshot", "bezel", "boxart",
                   "cartridge", "mix", "wheel", "map", "video", "manual", "magazine", "music"}
GAMELIST_FILES = {"esde": "gamelist.xml", "knulli": "gamelist.xml", "onion": "miyoogamelist.xml"}


def gamelist_fields(meta):
    """gamelist.xml tags (as text) for one ROM's stored metadata."""
    out = {f: meta[f] for f in TEXT_FIELDS if f in meta}
    if "rating" in meta:
        out["rating"] = format(meta["rating"], "g")
    if "releasedate" in meta:
        out["releasedate"] = meta["releasedate"].replace("-", "") + "T000000"
    return out


def scrape_index(listing):
    """{ROM path without extension: {media type: (key, size)}} from a listing of scrapes/<system>/."""
    index = defaultdict(dict)
    for key, size in sorted(listing.items()):
        parts = key.split("/")
        if len(parts) > 3 and parts[2] in BUCKET_MEDIA:
            index[os.path.splitext("/".join(parts[3:]))[0]].setdefault(parts[2], (key, size))
    return index


def plan_scrapes(layout_name, rom_rels, listing, meta, media_root, rom_dir, present):
    """Media downloads and gamelist entries for one system's ROMs.

    rom_rels: ROM paths in the system folder; media_root: the esde media folder of the system;
    rom_dir: the system's ROM folder on the card; present(rom): is that ROM (going to be) on the card.
    Returns (jobs [(key, local path, size)], entries {ROM path: {gamelist tag: text}}).
    """
    index = scrape_index(listing)
    jobs, entries = [], {}
    for rom in sorted(rom_rels):
        if not present(rom):
            continue
        stem = os.path.splitext(rom)[0]
        found = index.get(stem, {})
        tags = gamelist_fields(meta.get(rom, {}))
        base = os.path.basename(stem)
        if layout_name == "esde":
            for mtype, (key, size) in found.items():
                if mtype in MEDIA_TYPES:  # not the Onion-only art
                    jobs.append((key, os.path.join(media_root, mtype, key.split("/", 3)[3]), size))
        elif layout_name == "knulli":
            for tag, folder, suffix, types in KNULLI_MEDIA:
                mtype = next((t for t in types if t in found), None)
                if mtype:
                    key, size = found[mtype]
                    name = f"{base}-{suffix}{os.path.splitext(key)[1]}"
                    jobs.append((key, os.path.join(rom_dir, folder, name), size))
                    tags[tag] = f"./{folder}/{name}"
        elif layout_name == "onion":
            if "/" in rom:  # Onion's Imgs folder is flat and its gamelist ignores subfolders
                continue
            tags = {"name": tags["name"]} if "name" in tags else {}
            if ONION_TYPE in found:
                key, size = found[ONION_TYPE]
                jobs.append((key, os.path.join(rom_dir, "Imgs", base + ".png"), size))
                tags["image"] = f"./Imgs/{base}.png"
        if tags:
            entries[rom] = tags
    return jobs, entries


def can_shrink():
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return bool(shutil.which("sips"))


def shrink_png(src, dst, box=ONION_MAX):
    """Write src as a PNG that fits in box (never enlarged), with Pillow or macOS sips."""
    try:
        from PIL import Image
    except ImportError:
        Image = None
    if Image:
        with Image.open(src) as im:
            im.thumbnail(box)
            im.save(dst, "PNG", optimize=True)
        return
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", src],
                         check=True, capture_output=True, text=True).stdout
    w, h = (int(re.search(rf"{k}: (\d+)", out).group(1)) for k in ("pixelWidth", "pixelHeight"))
    scale = min(1, box[0] / w, box[1] / h)
    subprocess.run(["sips", "-s", "format", "png", "-z", str(max(1, round(h * scale))), str(max(1, round(w * scale))),
                    src, "--out", dst], check=True, capture_output=True)


def update_gamelist(path, entries):
    """Set the given tags on each ROM's <game> in a gamelist file, creating the file and entries as needed.

    Everything else in the file is kept (favorites, play counts, an <alternativeEmulator> block...).
    Returns True if the file was written.
    """
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
    m = re.search(r"<gameList\b[^>]*/>", text) or re.search(r"<gameList\b.*</gameList>", text, re.S)
    prefix = text[:m.start()] if m else '<?xml version="1.0"?>\n'
    root = ET.fromstring(m.group(0)) if m else ET.Element("gameList")
    games = {(g.findtext("path") or "").strip(): g for g in root.findall("game")}
    changed = not m
    for rom, tags in entries.items():
        game = games.get("./" + rom)
        if game is None:
            game = ET.SubElement(root, "game")
            ET.SubElement(game, "path").text = "./" + rom
            games["./" + rom] = game
            changed = True
        for tag, value in tags.items():
            el = game.find(tag)
            if el is None:
                el = ET.SubElement(game, tag)
            if el.text != value:
                el.text = value
                changed = True
    if not changed:
        return False
    ET.indent(root, space="\t")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(prefix + ET.tostring(root, encoding="unicode") + "\n")
    return True


def setting_line(name, value):
    if isinstance(value, bool):
        return f'<bool name="{name}" value="{str(value).lower()}" />'
    if isinstance(value, int):
        return f'<int name="{name}" value="{value}" />'
    return f'<string name="{name}" value="{escape(str(value), {chr(34): "&quot;"})}" />'


def update_settings(text, settings):
    """es_settings.xml text with the given typed settings set: lines replaced in place, missing ones added."""
    lines = text.splitlines() or ['<?xml version="1.0"?>']
    todo = {k: v for k, v in settings.items() if share_setting(k)}
    for i, line in enumerate(lines):
        m = SETTING_LINE.search(line)
        if m and m.group(2) in todo:
            lines[i] = setting_line(m.group(2), todo.pop(m.group(2)))
    lines += [setting_line(k, v) for k, v in todo.items()]
    return "\n".join(lines) + "\n"


def plan_esde_extras(es_dir, listing, texts):
    """Themes, collections and settings from scrapes/esde/ that the card is missing or has older.

    listing: {key: size} under scrapes/esde/; texts: {key: text} of its collections and settings.json.
    Returns (download jobs, [(path, text)] to write).
    """
    prefix = f"{SCRAPES}/esde/"
    jobs = [(key, os.path.join(es_dir, "themes", key[len(prefix + "themes/"):]), size)
            for key, size in sorted(listing.items()) if key.startswith(prefix + "themes/") and not key.endswith("/")]
    writes = []
    for key, text in sorted(texts.items()):
        if key.startswith(prefix + "collections/") and key.endswith(".cfg"):
            path = os.path.join(es_dir, "collections", key[len(prefix + "collections/"):])
        elif key == prefix + "settings.json":
            path = os.path.join(es_dir, "settings", "es_settings.xml")
        else:
            continue
        old = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                old = f.read()
        if key.endswith(".cfg"):
            new = merge_lines(old, text)
            changed = new.splitlines() != old.splitlines()
        else:
            try:
                new = update_settings(old, json.loads(text))
            except ValueError:
                continue
            changed = new != old
        if changed:
            writes.append((path, new))
    return plan_downloads(jobs), writes


def load_scrape_data(systems, esde):
    """The bucket's scrape data for the chosen systems: {bucket folder: (listing, metadata)}, plus the
    shared scrapes/esde/ listing and texts when the layout is esde."""
    with ThreadPoolExecutor(WORKERS) as ex:
        listings = list(ex.map(lambda s: list_sizes(f"{SCRAPES}/{s['bucket']}/"), systems))
    extra = list_sizes(f"{SCRAPES}/esde/") if esde else {}
    meta_keys = [f"{SCRAPES}/{s['bucket']}/metadata.json" for s, l in zip(systems, listings)
                 if f"{SCRAPES}/{s['bucket']}/metadata.json" in l]
    texts = fetch_texts(meta_keys + [k for k in extra if k.endswith(".cfg") or k.endswith("/settings.json")])
    data = {}
    for s, listing in zip(systems, listings):
        key = f"{SCRAPES}/{s['bucket']}/metadata.json"
        try:
            meta = json.loads(texts[key]) if key in texts else {}
        except ValueError:
            meta = {}
        data[s["bucket"]] = (listing, meta)
    return data, extra, {k: v for k, v in texts.items() if k.startswith(f"{SCRAPES}/esde/")}


def build_scrape_plan(layout_name, systems, data, extra, extra_texts, rom_rels, dest_of, es_dir, present):
    """Everything a sync installs from scrapes/: media jobs, gamelist entries per file, ES-DE extras."""
    plan = {"jobs": [], "gamelists": defaultdict(dict), "extras": [], "writes": []}
    for s in systems:
        listing, meta = data[s["bucket"]]
        rom_dir = dest_of(s)
        media_root = os.path.join(es_dir, "downloaded_media", s["bucket"])
        jobs, entries = plan_scrapes(layout_name, rom_rels.get(s["bucket"], ()), listing, meta, media_root, rom_dir,
                                     lambda rom, d=rom_dir: present(os.path.join(d, rom)))
        plan["jobs"] += plan_downloads(jobs)
        if entries:
            gl = (os.path.join(es_dir, "gamelists", s["bucket"]) if layout_name == "esde" else rom_dir)
            plan["gamelists"][os.path.join(gl, GAMELIST_FILES[layout_name])].update(entries)
    if layout_name == "esde":
        plan["extras"], plan["writes"] = plan_esde_extras(es_dir, extra, extra_texts)
    return plan


def describe_scrape_plan(plan):
    jobs = plan["jobs"] + plan["extras"]
    print(f"🖼️  Scraped data: {bold(str(len(jobs)))} file(s) to download "
          f"({human_size(sum(j[2] or 0 for j in jobs))}), {len(plan['gamelists'])} gamelist file(s) to update"
          + (f", {len(plan['writes'])} collection/settings file(s)" if plan["writes"] else ""))


def apply_scrape_plan(plan, base):
    """Download the media, then write the gamelists, collections and settings. Returns failures."""
    failed = run_downloads(plan["jobs"] + plan["extras"], "Scraped data", "🖼️", base)
    for path, entries in plan["gamelists"].items():
        try:
            update_gamelist(path, entries)
        except (ET.ParseError, OSError, UnicodeDecodeError) as e:
            failed += 1
            print(red(f"  ❌ {path}: {e}"))
    for path, text in plan["writes"]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    return failed


def card_stems(rom_dir, flat):
    """ROM names without extension in a system's ROM folder (base names only if flat)."""
    stems = set()
    for root, files in walk_roms(rom_dir):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), rom_dir).replace(os.sep, "/")
            stems.add(os.path.splitext(os.path.basename(rel) if flat else rel)[0])
    return stems


def stale_media(layout_name, systems, roms_dir, es_dir):
    """Media files on the card whose ROM isn't in the system's ROM folder, for every system in the
    layout (not just the ones being synced). Systems with no ROM folder are left alone."""
    stale, seen = [], set()
    for s in systems:
        folder = s["folders"].get(layout_name)
        rom_dir = os.path.join(roms_dir, folder) if folder else None
        if not rom_dir or rom_dir in seen or not os.path.isdir(rom_dir):
            continue
        seen.add(rom_dir)
        stems = card_stems(rom_dir, layout_name != "esde")
        if layout_name == "esde":
            for mtype in sorted(MEDIA_TYPES):
                base = os.path.join(es_dir, "downloaded_media", folder, mtype)
                stale += [full for rel, full in walk_files(base) if os.path.splitext(rel)[0] not in stems] \
                    if os.path.isdir(base) else []
        elif layout_name == "knulli":
            for sub in ("images", "videos", "manuals"):
                base = os.path.join(rom_dir, sub)
                for rel, full in walk_files(base) if os.path.isdir(base) else []:
                    name = os.path.splitext(os.path.basename(rel))[0]
                    if name not in stems and not any(name.endswith("-" + x) and name[:-len(x) - 1] in stems
                                                     for x in KNULLI_SUFFIXES):
                        stale.append(full)
        else:
            base = os.path.join(rom_dir, "Imgs")
            stale += [full for rel, full in walk_files(base) if os.path.splitext(os.path.basename(rel))[0] not in stems] \
                if os.path.isdir(base) else []
    return stale


# --- Local mirror ---------------------------------------------------------------------------------

def load_settings():
    """Saved global settings: {"bucket": S3 bucket name, "mirror": folder of the local mirror}."""
    try:
        with open(os.path.join(data_dir(), "settings.json")) as f:
            settings = json.load(f)
    except (OSError, ValueError):
        return {}
    return settings if isinstance(settings, dict) else {}


def save_setting(name, value):
    """Set a global setting, or remove it when value is None."""
    settings = load_settings()
    if value is None:
        settings.pop(name, None)
    else:
        settings[name] = value
    try:
        os.makedirs(data_dir(), exist_ok=True)
        with open(os.path.join(data_dir(), "settings.json"), "w") as f:
            json.dump(settings, f, indent=2, sort_keys=True)
    except OSError as e:
        raise SystemExit(red(f"❌ Couldn't save the setting: {e}"))


def ensure_bucket():
    """Set BUCKET from the saved settings, asking for it (and saving it) on first run."""
    global BUCKET
    BUCKET = load_settings().get("bucket")
    while not BUCKET:
        try:
            name = input("🪣 Which S3 bucket holds your ROMs? ").strip()
        except EOFError:
            raise SystemExit(red("❌ No bucket given"))
        name = re.sub(r"^s3://", "", name).strip("/")
        if name:
            save_setting("bucket", name)
            BUCKET = name


def mirror_wanted(manifest):
    """{bucket key: size} of everything the game lists and BIOS requirements reference that is in the bucket: the ROMs a sync
    installs, every system's BIOS files, the scraped data of those ROMs, and all of scrapes/esde/."""
    systems = manifest["systems"]
    todo = [s for s in systems if s.get("full_system") or listed(s)]
    with ThreadPoolExecutor(WORKERS) as ex:
        roms = list(ex.map(lambda s: list_sizes(s["bucket"] + "/"), todo))
        scrapes = list(ex.map(lambda s: list_sizes(f"{SCRAPES}/{s['bucket']}/"), todo))
    wanted = {}
    for s, have, scraped in zip(todo, roms, scrapes):
        keys = [k for k in available_keys(s, have) if k in have]
        wanted.update((k, have[k]) for k in keys)
        stems = {os.path.splitext(k.split("/", 1)[1])[0] for k in keys}
        for key, size in scraped.items():
            parts = key.split("/")
            if key == f"{SCRAPES}/{s['bucket']}/metadata.json" or (
                    len(parts) > 3 and parts[2] in BUCKET_MEDIA and os.path.splitext("/".join(parts[3:]))[0] in stems):
                wanted[key] = size
    bios = list_sizes("BIOS/")
    for s in systems:
        for f in s["bios"]["files"]:
            if "BIOS/" + f in bios:
                wanted["BIOS/" + f] = bios["BIOS/" + f]
    wanted.update((k, v) for k, v in list_sizes(f"{SCRAPES}/esde/").items() if not k.endswith("/"))
    return wanted


def refresh_mirror(root, dry_run=False):
    """Make root hold exactly what the game lists reference: download what's missing or a different size,
    delete the rest. Returns the number of failed downloads."""
    if not os.path.exists(os.path.join(root, MIRROR_MARKER)):
        if os.path.isdir(root) and os.listdir(root):
            raise SystemExit(red(f"❌ {root} isn't empty and isn't a sync-roms mirror"))
        if not dry_run:
            os.makedirs(root, exist_ok=True)
            open(os.path.join(root, MIRROR_MARKER), "w").close()
    print("📄 Fetching manifests...")
    manifest = load_manifest()
    print("📏 Listing the bucket...")
    wanted = mirror_wanted(manifest)
    have = {k: s for k, s in local_sizes(root).items() if k != MIRROR_MARKER}
    todo = plan_downloads([(k, os.path.join(root, *k.split("/")), s) for k, s in wanted.items()])
    stale = sorted(set(have) - set(wanted))
    print(f"🪞 Mirror: {bold(str(len(todo)))} to download ({human_size(sum(j[2] for j in todo))}), "
          f"{len(wanted) - len(todo)} up to date, {bold(str(len(stale)))} to delete")
    if dry_run:
        for key, _, _ in todo:
            print(f"  {key}")
        for key in stale:
            print(f"  {red('would delete')} {key}")
        return 0
    failed = run_downloads(todo, "Mirror", "🪞", root)
    for key in stale:
        os.remove(os.path.join(root, *key.split("/")))
    for folder, _, _ in os.walk(root, topdown=False):
        if folder != root and not os.listdir(folder):
            os.rmdir(folder)
    if stale:
        print(green(f"  🧹 Deleted {len(stale)} file(s) no longer referenced"))
    return failed


def use_mirror(root, dry_run):
    """Refresh the saved mirror from the bucket, then make this run read from it."""
    global _mirror_root
    if not os.path.exists(os.path.join(root, MIRROR_MARKER)):
        print(yellow(f"  ⚠️  Mirror {root} not found; using the bucket"))
        return
    print(bold(f"🪞 Local mirror {cyan(root)}"))
    try:
        refresh_mirror(root, dry_run)
    except (subprocess.CalledProcessError, OSError, SystemExit) as e:  # aws failed, or the folder isn't a mirror
        print(yellow(f"  ⚠️  Couldn't refresh the mirror ({getattr(e, 'stderr', None) or e}); using what it has"))
    _mirror_root = root


def mirror_command(args):
    if args.clear_mirror:
        save_setting("mirror", None)
        print(green("🪞 Mirror setting cleared") + dim(" (the mirror's files are left alone)"))
        return 0
    given = args.use_mirror or args.mirror
    root = given or load_settings().get("mirror")
    if not root:
        raise SystemExit(red("❌ No mirror folder: give one (--mirror DIR) or save one with --use-mirror DIR"))
    root = os.path.abspath(os.path.expanduser(root))
    print(bold(f"🪞 Mirror {cyan(root)}") + dim(f"  s3://{BUCKET}  profile={PROFILE}"))
    failed = refresh_mirror(root, args.dry_run)
    if args.use_mirror and not args.dry_run:
        save_setting("mirror", root)
        print(green(f"💾 Saved {root} as the local mirror"))
    print(green("\n🎉 Done!") if not failed else red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0


def main():
    try:
        return sync()
    except KeyboardInterrupt:
        print(yellow("\n🛑 Interrupted"))
        return 130
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)  # dot_clean inherits this, so a second ^C can't cut it short
        clean_dirs()


def list_devices():
    """Print a table of the devices: name, chip and number of recommended systems."""
    devices = load_manifest()["devices"]
    rows = [(d["name"], d["soc"], str(len(d["systems"]))) for d in devices]
    head = ("Device", "Chip", "Systems")
    widths = [max(len(r[i]) for r in rows + [head]) for i in range(3)]
    print(bold(f"{head[0]:<{widths[0]}}  {head[1]:<{widths[1]}}  {head[2]:>{widths[2]}}"))
    for name, soc, count in rows:
        print(f"{name:<{widths[0]}}  {soc:<{widths[1]}}  {count:>{widths[2]}}")
    return 0


def sync():
    global _clean_root
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("base_dir", nargs="?")
    ap.add_argument("-n", "--dry-run", action="store_true")
    ap.add_argument("-e", "--edit", action="store_true")
    ap.add_argument("-a", "--ask", action="store_true")
    ap.add_argument("-u", "--upload-scrapes", action="store_true")
    ap.add_argument("-c", "--clean-scrapes", action="store_true")
    ap.add_argument("--mirror", nargs="?", const="")
    ap.add_argument("--use-mirror")
    ap.add_argument("--clear-mirror", action="store_true")
    ap.add_argument("--devices", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    args = ap.parse_args()
    if args.help:
        print(help_text())
        return 0
    if args.devices:
        return list_devices()
    ensure_bucket()
    mirror_mode = args.mirror is not None or bool(args.use_mirror) or args.clear_mirror
    if args.edit + args.upload_scrapes + args.clean_scrapes + mirror_mode > 1:
        raise SystemExit(red("❌ Use only one of --edit, --upload-scrapes, --clean-scrapes, --mirror, "
                             "--use-mirror and --clear-mirror"))
    if mirror_mode:
        return mirror_command(args)
    if args.edit or args.upload_scrapes or args.clean_scrapes:
        code = edit_manifest() if args.edit else upload_scrapes(args) if args.upload_scrapes else clean_scrapes(args)
        mirror = load_settings().get("mirror")
        if mirror and not code and not args.dry_run:  # pick up the games just added
            print()
            use_mirror(mirror, False)
        return code
    base = os.path.abspath(os.path.expanduser(args.base_dir or os.getcwd()))

    print(bold(f"🎮 sync-roms") + dim(f"  s3://{BUCKET}  profile={PROFILE}"))
    if load_settings().get("mirror"):
        use_mirror(load_settings()["mirror"], args.dry_run)
    print("📄 Fetching manifests...")
    manifest = load_manifest()
    systems = manifest["systems"]
    devices, layouts = manifest["devices"], manifest["layouts"]
    card = os.path.basename(base) or base
    saved = load_cards().get(card)
    dirs = None
    if isinstance(saved, dict) and saved.get("layout") in layouts:
        device = next((d for d in devices if d["id"] == saved.get("device")), None)
        if device or saved.get("device") == "full":
            layout_name = saved["layout"]
            print(bold(f"💾 Remembered {cyan(card)}: ")
                  + f"{device['name'] if device else 'Full'} · {layouts[layout_name]['label']}")
            if not args.ask or confirm("Use this saved setup?"):
                dirs = prepare_dirs(base, layouts[layout_name], args.dry_run, ask=False)
    if dirs is None:
        device, layout_name = choose_setup(manifest)
        dirs = prepare_dirs(base, layouts[layout_name], args.dry_run)
        if dirs is None:
            raise SystemExit(yellow("👋 Cancelled."))
        if not args.dry_run:
            save_card(card, device, layout_name)
    layout = layouts[layout_name]
    roms_dir, bios_dir = dirs
    if not args.dry_run:
        _clean_root = base
    if device:
        wanted_ids = set(device["systems"])
        systems = [s for s in systems if s["bucket"] in wanted_ids]
        if device["note"]:
            print(dim(f"  {device['name']}: {device['note']}"))
    unsupported = [s for s in systems if not s["folders"].get(layout_name)]
    if unsupported:
        systems = [s for s in systems if s["folders"].get(layout_name)]
        print(dim(f"  {len(unsupported)} system(s) have no {layout['label']} folder and are skipped"))
    systems.sort(key=lambda s: s["name"].lower())

    print("📏 Reading ROM sizes...")
    with ThreadPoolExecutor(WORKERS) as ex:
        listings = dict(zip((s["bucket"] for s in systems),
                            ex.map(lambda s: list_sizes(s["bucket"] + "/")
                                   if s.get("full_system") or listed(s) else {}, systems)))

    def available(s):
        return available_keys(s, listings[s["bucket"]])

    def sizes(s):
        """(bytes still to download, total bytes) for a system's ROMs."""
        have, need, total = listings[s["bucket"]], 0, 0
        for k in available(s):
            size = have.get(k, 0)
            total += size
            if plan_downloads([(k, os.path.join(roms_dir, s["folders"][layout_name], k.split("/", 1)[1]), size)]):
                need += size
        return need, total

    rows = [(f"{s['name']}  ({len(available(s))} roms)", bool(available(s)), *sizes(s)) for s in systems]
    present = [i for i, s in enumerate(systems)
               if available(s) and (device or has_local_files(os.path.join(roms_dir, s["folders"][layout_name])))]
    chosen = pick_systems(rows, present)
    if not chosen:
        print(yellow("👋 Nothing selected."))
        return 0
    chosen = [systems[i] for i in chosen]
    print(bold(f"\n🔎 Checking {len(chosen)} system(s) against the bucket..."))

    def dest_of(s):
        return os.path.join(roms_dir, s["folders"][layout_name])

    rom_jobs, missing, extras = [], [], []
    for s in chosen:
        wanted = available(s)
        if not wanted:
            continue
        have = listings[s["bucket"]]
        dest = dest_of(s)
        for key in wanted:
            if key in have:
                rom_jobs.append((key, os.path.join(dest, key.split("/", 1)[1]), have[key]))
            else:
                missing.append(key)
    report_missing(missing, "ROM(s)")
    # systems can share a folder (Onion: WS, NGP), so a folder's expected files are the union over all of them
    for dest in sorted({dest_of(s) for s in chosen if available(s)}):
        extras += find_extras(dest, [k for t in systems if dest_of(t) == dest for k in available(t)])

    bios_keys = sorted({"BIOS/" + f for s in chosen for f in s["bios"]["files"]})
    bios_have = list_sizes("BIOS/") if bios_keys else {}
    bios_jobs = [(k, os.path.join(bios_dir, k[len("BIOS/"):]), bios_have[k])
                 for k in bios_keys if k in bios_have]
    report_missing([k for k in bios_keys if k not in bios_have], "BIOS file(s)")

    rom_todo, bios_todo = plan_downloads(rom_jobs), plan_downloads(bios_jobs)
    print(f"\n💿 ROMs: {bold(str(len(rom_todo)))} to download "
          f"({human_size(sum(j[2] or 0 for j in rom_todo))}), "
          f"{len(rom_jobs) - len(rom_todo)} already present")
    print(f"🧠 BIOS: {bold(str(len(bios_todo)))} to download "
          f"({human_size(sum(j[2] or 0 for j in bios_todo))}), "
          f"{len(bios_jobs) - len(bios_todo)} already present")
    if extras:
        print(f"🗑️  Local ROMs no longer in the selection: {bold(str(len(extras)))}")
    es_dir = os.path.join(base, "ES-DE")
    scraped = {}

    def scrape_plan(present):
        if not scraped:
            print("🖼️  Reading scraped data...")
            scraped["data"] = load_scrape_data(chosen, layout_name == "esde")
            scraped["rels"] = {s["bucket"]: [k.split("/", 1)[1] for k in available(s) if k in listings[s["bucket"]]]
                               for s in chosen}
        return build_scrape_plan(layout_name, chosen, *scraped["data"], scraped["rels"], dest_of, es_dir, present)

    if args.dry_run:
        print(yellow("\n🧪 Dry run — nothing downloaded or deleted"))
        for key, path, _ in rom_todo + bios_todo:
            print(f"  {key} {dim('→')} {path}")
        for path in extras:
            print(f"  {red('would delete')} {path}")
        describe_scrape_plan(scrape_plan(lambda path: True))
        print(f"🧹 Media on the card for ROMs it doesn't have: {len(stale_media(layout_name, manifest['systems'], roms_dir, es_dir))} file(s) to remove")
        if layout_name == "esde":
            clean_android_media(base, card, True, args.ask)
        return 0

    if extras:
        for path in extras[:10]:
            print(dim(f"     {path}"))
        if len(extras) > 10:
            print(dim(f"     … and {len(extras) - 10} more"))
        if confirm(f"🗑️  Delete these {len(extras)} local file(s)?", default=False):
            for path in extras:
                os.remove(path)
            print(green(f"  🧹 Deleted {len(extras)} file(s)"))
        else:
            print(yellow("  ↩️  Keeping them"))

    failed = run_downloads(rom_todo, "ROMs", "💿", roms_dir) + run_downloads(bios_todo, "BIOS", "🧠", bios_dir)
    plan = scrape_plan(os.path.exists)
    describe_scrape_plan(plan)
    failed += apply_scrape_plan(plan, base)
    stale = stale_media(layout_name, manifest["systems"], roms_dir, es_dir)
    for path in stale:
        try:
            os.remove(path)
        except OSError as e:
            print(red(f"  ❌ {path}: {e}"))
    if stale:
        print(green(f"🧹 Removed {len(stale)} media file(s) for ROMs that aren't on this card"))
    if layout_name == "esde":  # only Android cards have these folders; a Knulli card's "music" must stay
        clean_android_media(base, card, False, args.ask)
    print(green("\n🎉 Done!") if not failed else red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Download ROMs and BIOS files from the roms bucket."""
import argparse
import curses
import hashlib
import io
import json
import mimetypes
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from types import SimpleNamespace
from xml.sax.saxutils import escape, unescape

import boto3
from boto3.s3.transfer import TransferConfig, create_transfer_manager
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, ProfileNotFound
from s3transfer.subscribers import BaseSubscriber

BUCKET = None  # set by ensure_bucket() from settings.json
ENDPOINT = None  # custom S3 endpoint URL from settings.json; None means AWS
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
  {green('sync-roms')} [{yellow('--dry-run')}] [{cyan('BASE_DIR')}]   {dim('(no folder: BASE_DIR is the current directory)')}

{bold('ARGUMENTS')}
  {cyan('BASE_DIR')}   📦 the card or folder root. The chosen layout decides the folders inside it
              {dim('(ES-DE ROMs/ BIOS/, Knulli roms/ bios/, Onion Roms/ BIOS/)')}

  Missing folders are created after you confirm; if they can't be created
  (no permission) the script stops before asking.

{bold('OPTIONS')}
  {yellow('-n, --dry-run')}   show what would be downloaded, download nothing
  {yellow('-e, --edit')}      ✏️  add/remove games in the core list (every card) or a card's extras, by system or set (type to filter);
                      {yellow('^F')} toggles a whole set or system. {dim('(no folders needed; saves ~/.sync-roms/games.json and cards.json)')}
  {yellow('-a, --ask')}           ❓ confirm the saved settings (device and layout, Android media folders) instead of using them silently;
                      answering no asks the question again and saves the new answer
  {yellow('-u, --upload-scrapes')} [{cyan('BASE_DIR')}]   ☁️  upload BASE_DIR/ES-DE scraped data (metadata, media, themes, collections,
                      settings) to the bucket's scrapes/ folder, merging with what's there
                      {dim('(only the safe-to-share metadata fields are kept; uploads with the ROMS_WRITE_PROFILE profile)')}
  {yellow('--upload')} [{cyan('DIR')}]   ☁️  upload the ROMs in DIR (no DIR: the current directory) and its subfolders to the bucket folder of a system you pick
                      {dim('(the system is guessed from the folder name; files with the same size are skipped, a different size overwrites after you confirm;')}
                      {dim('uploads in parallel, several requests per CPU core, with the ROMS_WRITE_PROFILE profile; works with --dry-run)')}
  {yellow('--replace')}   {dim('with --upload: make the bucket folder match DIR — renamed files are moved in the bucket by content, new and changed ones uploaded,')}
                      {dim('and the bucket files left over (not renames) are listed so you pick which to delete and which to keep')}
  {yellow('--diff')} [{cyan('DIR')}]   🔍 list the ROMs in only one of DIR (no DIR: the current directory) and the bucket folder of a system you pick, ignoring renames
                      {dim('(same path and size is the same file; the rest are matched by content: the CRCs inside zips, read from the zip index of just those files)')}
  {yellow('-c, --clean-scrapes')}   🧹 remove scrapes/ media and metadata for ROMs that aren't in the bucket at all (asks first, no folder needed)
  {yellow('--m3u')} [{cyan('DIR')}]   💿 create or fix the .m3u playlist of every multi-disc game ("Name (Disc 1) (Extra).chd", "Name (Disc 2).chd") in DIR
                      and its subfolders (no DIR: the current directory); playlists whose files are all missing are deleted (asks first),
                      ones with the wrong or some missing discs are rewritten, and ones with the right discs under another name are renamed {dim('(local only; works with --dry-run)')}
  {yellow('--chd')} [{cyan('DIR')}]   📀 unzip (7z) every .zip/.7z and convert each disc image (.cue, .gdi, .toc, .iso) to a verified .chd, per the chd setting of the
                      system whose folder it is in (DIR can be one system folder or hold several; no DIR: the current directory); archives and
                      images are removed once their chd verifies, then the .m3u playlists are fixed (always, even with nothing to convert); files convert in parallel, up to one per CPU core, with a progress bar. GameCube and Wii archives are only unzipped
                      {dim('(needs 7z and chdman, see --install-tools; works with --dry-run)')}
  {yellow('--install-tools')}   🍺 brew install the 7z (sevenzip) and chdman (rom-tools) that --chd needs, whichever are missing
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
      then its firmware (ES-DE, Knulli, muOS, Onion or Slot; the firmware decides the folder layout, and a device with one firmware isn't asked). Type to filter, enter continues, esc goes back.
      The choice is remembered per BASE_DIR folder name (in the user data folder) and used without asking next
      time. With --ask it is confirmed first; answer n to pick again.
  2️⃣  Toggle systems on/off (for a device, its recommended systems start on; otherwise systems whose folder already has files start on, the rest off; systems with no ROMs are hidden, press e shows them last)
  3️⃣  ROMs download, then BIOS for the chosen systems
  4️⃣  Scraped data (media, descriptions...) for the chosen systems' games is installed from the bucket's scrapes/ folder
      for the firmware: ES-DE (ES-DE/ folder), Knulli (images/videos/manuals and gamelist.xml), Onion (Imgs/ and
      miyoogamelist.xml), muOS (catalogue box/preview/text) or Slot (cart labels). ES-DE also gets its themes, collections and the shared settings every time.
      Then media on the card for ROMs the card doesn't have is removed, for every system, no questions asked.

{bold('PICKER KEYS')}
  {yellow('↑/↓ j/k')} move   {yellow('PgUp/PgDn')} page   {yellow('space/tab')} toggle
  {yellow('a')} all on   {yellow('n')} all off   {yellow('e')} show/hide 0-ROM systems
  {yellow('enter')} confirm   {yellow('q')} quit

{bold('ENVIRONMENT')}
  {yellow('ROMS_BUCKET')}    S3 bucket name (overrides settings.json "bucket")
  {yellow('ROMS_ENDPOINT')}  custom S3 endpoint URL (overrides settings.json "endpoint"; default: AWS)
  {yellow('ROMS_PROFILE')}   aws profile to use (overrides settings.json "profile"; default: roms-readonly)
  {yellow('ROMS_WRITE_PROFILE')}   aws profile used to upload and clean scrapes (overrides "write_profile"; default: roms)
  {yellow('NO_COLOR')}       disable colors

{bold('NOTES')}
  ⚡ Files already present locally with the same size are skipped.
  🗑️  Local ROMs no longer in a chosen system's list are listed and, after you
     confirm (default no), deleted. Other systems' folders and BIOS are never touched.
     Frontend files are ignored: dotfiles, ES-DE systeminfo.txt/noload.txt, Knulli _info.txt,
     gamelist.xml and images/ videos/ manuals/ folders, Onion miyoogamelist.xml and Imgs/, Thumbs.db.
  📄 games.json lives in ~/.sync-roms/ (copied from the repo's version on first run) and is never read from the
     bucket. It is the core list every card gets; a card's own extra games are saved in cards.json and add to it.
     A list can also name whole sets: "sets": ["mario", "zelda"]. Optional ~/.sync-roms/device-systems.json adjusts a device's recommended systems:
     {{"miyoo-flip-v2": {{"add": ["psx"], "remove": ["gba"]}}}}
"""


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
        s["games"] = [g for g in entry if isinstance(g, dict)] if isinstance(entry, list) else []
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


SETS_KEY = "sets"  # reserved key in a games list: ids of whole game sets to sync
_warned = set()  # warnings already printed this run, so a menu redraw doesn't repeat them


def card_games(card):
    """The extra games list saved for a card in cards.json ({} when it has none)."""
    entry = load_cards().get(card)
    games = entry.get("games") if isinstance(entry, dict) else None
    return games if isinstance(games, dict) else {}


def all_card_names():
    return sorted(load_cards())


def list_sets(games):
    """The set ids a games list references; anything that isn't a list of strings is ignored."""
    ids = games.get(SETS_KEY, [])
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        if SETS_KEY not in _warned:
            _warned.add(SETS_KEY)
            print(f"warning: games: {SETS_KEY!r} must be a list of set ids, ignored (saving that list drops it)",
                  file=sys.stderr)
        return [i for i in ids if isinstance(i, str)] if isinstance(ids, list) else []
    return ids


def set_games(game_set):
    """A set's games as {"title", "bucket", "system"} entries, with each game's extra files as entries of their own."""
    out, seen = [], set()
    for g in game_set["games"]:
        for key in [g.get("bucket")] + list(g.get("files", [])):
            if key and key not in seen:
                seen.add(key)
                title = g.get("title") if key == g.get("bucket") and g.get("title") \
                    else os.path.splitext(key.split("/", 1)[-1])[0]
                out.append({"title": title, "bucket": key, "system": g.get("system")})
    return out


def merge_lists(systems, lists, sets):
    """Set each system's games/full_system to the union of the games lists and the sets they reference.

    A list is {system bucket: [games] | {"full_system": true}, "sets": [set ids]}. Games go in the order
    lists come, direct games before set games, deduplicated by bucket key.
    """
    by_id = {x["id"]: x for x in sets}
    for s in systems:
        s["games"], s["full_system"] = [], False
    by_bucket = {s["bucket"]: s for s in systems}

    def add(s, g):
        if g.get("bucket") and not any(x.get("bucket") == g["bucket"] for x in s["games"]):
            s["games"].append({k: v for k, v in g.items() if k != "system"})

    for raw in lists:
        for s in systems:
            entry = raw.get(s["bucket"])
            if isinstance(entry, dict):
                s["full_system"] = s["full_system"] or bool(entry.get("full_system"))
            elif isinstance(entry, list):
                for g in entry:
                    if isinstance(g, dict):
                        add(s, g)
    for raw in lists:
        for set_id in list_sets(raw):
            if set_id not in by_id:
                print(f"warning: games: unknown set {set_id!r}, skipped", file=sys.stderr)
                continue
            for g in set_games(by_id[set_id]):
                if g["system"] in by_bucket:
                    add(by_bucket[g["system"]], g)
    return systems


def load_manifest(card_names=()):
    """Systems, devices and layouts from the repo, joined with the personal games (plus the extras of the
    named cards) and device-system overlay."""
    seed_personal_files()
    manifest = {name: repo_json(name) for name in ("layouts", "systems", "devices")}
    lists = [personal_json("games.json")] + [card_games(n) for n in card_names]
    merge_lists(manifest["systems"], lists, load_sets())
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
    pages = s3_client().get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix)
    return {o["Key"]: o["Size"] for page in pages for o in page.get("Contents", [])}


def pick_device(devices, cursor=0):
    """Returns a device dict, "full", or None on Esc."""
    options = [(f"📟 {d['name']}", d) for d in devices] + [("🌍 Full (every system)", "full")]
    i = filter_list("🎯 Which device?", [label for label, _ in options], cursor=cursor,
                    hint="type to filter · ↑/↓ move · Enter continue · Esc quit")
    return None if i is None else options[i][1]


def pick_layout(layouts, default):
    """Returns a layout (firmware) name, or None on Esc. default: layout name the cursor starts on."""
    names = list(layouts)
    labels = [f"{l['label']}  ({l['roms_dir']}/ {l['bios_dir']}/)" for l in layouts.values()]
    i = filter_list("🗂️  Which firmware?", labels, cursor=names.index(default) if default in names else 0,
                    hint="type to filter · ↑/↓ move · Enter continue · Esc back")
    return None if i is None else names[i]


def device_layouts(device, layouts):
    """The layouts (firmwares) a device can run, in its own order: the first is its default."""
    return {name: layouts[name] for name in device["firmwares"]}


def saved_setup(saved, devices, layouts):
    """(device dict or None for Full, layout name) from a card's saved entry, or None if it no longer applies."""
    if not isinstance(saved, dict) or saved.get("layout") not in layouts:
        return None
    if saved.get("device") == "full":
        return None, saved["layout"]
    device = next((d for d in devices if d["id"] == saved.get("device")), None)
    return (device, saved["layout"]) if device and saved["layout"] in device["firmwares"] else None


def choose_setup(manifest):
    """Ask for the device, then its firmware (Esc steps back; a single firmware isn't asked).
    Returns (device dict or None for Full, layout name)."""
    devices, layouts = manifest["devices"], manifest["layouts"]
    while True:
        choice = pick_device(devices)
        if choice is None:
            raise SystemExit(yellow("👋 Cancelled."))
        device = choice if isinstance(choice, dict) else None
        offered = device_layouts(device, layouts) if device else layouts
        if len(offered) == 1:
            return device, next(iter(offered))
        layout = pick_layout(offered, next(iter(offered)))
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


def filter_list(title, labels, multi=False, initial=None, hint="", cursor=0, extras=None, locked=None, locked_note="",
                hotkeys=()):
    """Type-to-filter list. Every space-separated term must appear in a label (case-insensitive).

    Single mode returns the chosen index, or None on Esc. Multi mode (Tab toggles) returns the list of
    on/off states on both Enter and Esc (Esc keeps the changes). cursor: index the highlight starts on.
    extras: per label, a list of (text, color) drawn after it (color: green, red, cyan or dim);
    they are not matched by the filter.
    locked: optional per-label flags; those rows are greyed out, can't be toggled, and show locked_note
    (one string, or one per label).
    hotkeys: control keys that, in single mode, return (key, label index) for the highlighted row instead of an index.
    """
    os.environ.setdefault("ESCDELAY", "25")
    lowered = [l.lower() for l in labels]
    start = list(initial) if initial is not None else [False] * len(labels)
    locked = locked or [False] * len(labels)

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
        colors = {"green": green_a, "red": red_a, "cyan": cyan_a, "dim": curses.A_DIM}
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
            keys = ("↑/↓ move · Tab toggle · ^A toggle all shown · Enter/Esc done"
                    if multi else "↑/↓ move · Enter select · Esc finish")
            stdscr.addnstr(2, 0, hint or keys, w - 1, curses.A_DIM)
            for pos in range(top, min(len(vis), top + view)):
                i = vis[pos]
                attr = curses.A_REVERSE if pos == cur else 0
                if locked[i]:
                    line = f"🔒 {labels[i]}"
                    attr |= curses.A_DIM
                elif multi:
                    if state[i] == start[i]:
                        mark = "✅" if state[i] else "⬜"
                    else:
                        mark = "➕" if state[i] else "➖"
                        attr |= green_a if state[i] else red_a
                    line = f"{mark} {labels[i]}"
                else:
                    line = labels[i]
                stdscr.addnstr(pos - top + 3, 0, line, w - 1, attr)
                x = len(line)
                for text, color in (extras[i] if extras else []):
                    if x >= w - 1:
                        break
                    stdscr.addnstr(pos - top + 3, x, text, w - 1 - x, attr | colors[color])
                    x += len(text)
            added = sum(1 for a, b in zip(state, start) if a and not b)
            removed = sum(1 for a, b in zip(state, start) if b and not a)
            status = f"{len(vis)}/{len(labels)} shown"
            if multi:
                status += f" · +{added} −{removed} pending"
            if vis and locked[vis[cur]]:
                status = f"🔒 {locked_note[vis[cur]] if isinstance(locked_note, list) else locked_note}"
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
                return state if multi else None
            elif k in ("\n", "\r", curses.KEY_ENTER):
                if multi:
                    return state
                if vis:
                    return vis[cur]
            elif k == "\t" and multi and vis:
                if not locked[vis[cur]]:
                    state[vis[cur]] = not state[vis[cur]]
            elif k == "\x01" and multi and vis:
                free = [i for i in vis if not locked[i]]
                target = not all(state[i] for i in free)
                for i in free:
                    state[i] = target
            elif k in hotkeys and not multi and vis:
                return k, vis[cur]
            elif isinstance(k, str) and k.isprintable():
                query += k
                cur = top = 0
    return curses.wrapper(run)


def snapshot(data):
    return {s["bucket"]: {g["bucket"] for g in s.get("games", []) if g.get("bucket")}
            for s in data["systems"]}


def load_sets():
    """Game sets from the repo's data/sets/*.json, sorted by name.

    Each file is {"name", "description" (optional), "games": [{"title", "system", "bucket", "files" (optional)}]}.
    "files" are extra bucket keys (e.g. the discs of a multi-disc game) toggled together with "bucket".
    """
    folder = os.path.join(REPO_DATA, "sets")
    sets = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if name.endswith(".json"):
            with open(os.path.join(folder, name)) as f:
                data = json.load(f)
            sets.append({"id": name[:-5], "name": data.get("name", name[:-5]),
                         "description": data.get("description", ""), "games": data.get("games", [])})
    return sorted(sets, key=lambda x: x["name"].lower())


FULL_SYSTEM_NOTE = "Full system: every file in its folder is synced, so it can't be toggled"


def toggle_games(title, rows, extras=None, covered=None):
    """Multi-select over rows of (system, bucket key, game title, label); adds/removes games in each system in place.

    extras: {bucket key: [more bucket keys]} added or removed together with that row's key.

    Rows of a full system are shown on and locked: its whole bucket folder is synced.
    covered: optional callable (system, bucket key) -> note or None; rows with a note are shown on and locked
    with that note (e.g. games a set reference or core already syncs).
    """
    notes = [FULL_SYSTEM_NOTE if s.get("full_system") else covered(s, key) if covered else None
             for s, key, _, _ in rows]
    locked = [bool(n) for n in notes]
    initial = [l or any(g.get("bucket") == key for g in s["games"]) for l, (s, key, _, _) in zip(locked, rows)]
    state = filter_list(title, [label for *_, label in rows], multi=True, initial=initial, locked=locked,
                        locked_note=[n or "" for n in notes])
    for (s, key, name, _), on, was, lock in zip(rows, state, initial, locked):
        if lock:
            continue
        keys = [key] + list((extras or {}).get(key, []))
        if on and not was:
            for k in keys:
                if not any(g.get("bucket") == k for g in s["games"]):
                    s["games"].append({"title": name if k == key else os.path.splitext(k.split("/", 1)[-1])[0],
                                       "bucket": k})
        elif was and not on:
            s["games"] = [g for g in s["games"] if g.get("bucket") not in keys]


def set_rows(game_set, by_bucket, bucket_keys):
    """Rows for one set, sorted by system then title. Entries for unknown systems are skipped."""
    rows, seen = [], set()
    for g in game_set["games"]:
        s = by_bucket.get(g.get("system"))
        key = g.get("bucket")
        if not s or not key or key in seen:
            continue
        seen.add(key)
        title = g.get("title") or os.path.splitext(key.split("/", 1)[-1])[0]
        have = bucket_keys(s)
        warn = "" if s.get("full_system") or all(k in have for k in [key] + list(g.get("files", []))) \
            else "  ⚠️ not in bucket"
        rows.append((s, key, title, f"{s['name']} — {title}{warn}"))
    return sorted(rows, key=lambda r: (r[0]["name"].lower(), r[2].lower()))


def valid_card_name(name, existing):
    """Why name can't be a new card's folder name, or None if it can."""
    if not name.strip():
        return "A card needs a name."
    if "/" in name or os.sep in name:
        return "A card name is a folder name, so it can't contain a slash."
    if name in existing:
        return f"There is already a card named {name}."
    return None


def dump_list(systems, sets_on):
    """A games list as saved to games.json or a card's cards.json entry."""
    out = {s["bucket"]: {"full_system": True} if s["full_system"] else s["games"]
           for s in systems if s["full_system"] or s["games"]}
    if sets_on:
        out[SETS_KEY] = list(sets_on)
    return out


def save_lists(core, cards):
    """Write the core list (when given) to games.json and each card's list into its cards.json entry."""
    if core is not None:
        path = os.path.join(data_dir(), "games.json")
        with open(path + ".tmp", "w") as f:
            json.dump(core, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(path + ".tmp", path)
    for name, games in cards.items():
        update_card(name, games=games)


def cover_notes(sets_by_id, own_set_ids, core=None):
    """Why games are synced without being in the list being edited.

    Returns ({system bucket: note} for whole systems, {bucket key: note} for single games). The notes come from
    the list's own set references and, when editing a card, from the core list (a raw games list).
    """
    full, keys = {}, {}
    if core is not None:
        for bucket, entry in core.items():
            if isinstance(entry, dict) and entry.get("full_system"):
                full[bucket] = "From core: full system"
            elif isinstance(entry, list):
                for g in entry:
                    if isinstance(g, dict) and g.get("bucket"):
                        keys.setdefault(g["bucket"], "From core")
        for sid in list_sets(core):
            for g in set_games(sets_by_id[sid]) if sid in sets_by_id else []:
                keys.setdefault(g["bucket"], f"From core: {sets_by_id[sid]['name']}")
    for sid in own_set_ids:
        for g in set_games(sets_by_id[sid]) if sid in sets_by_id else []:
            keys.setdefault(g["bucket"], f"Full set: {sets_by_id[sid]['name']}")
    return full, keys


def toggle_set_ref(sets_on, set_id):
    """The set ids with set_id switched on or off."""
    return [i for i in sets_on if i != set_id] if set_id in sets_on else sets_on + [set_id]


def toggle_full_system(s):
    s["full_system"] = not s["full_system"]


FULL_KEY = "\x06"  # ^F
FULL_HINT = "type to filter · ↑/↓ move · Enter open · ^F toggle {what} · Esc back"


def new_target(label, raw, setup=None):
    """The editing state of one games list: its systems, set references and what they were when opened."""
    data = {"systems": apply_games(repo_json("systems"), raw)}
    sets_on = list_sets(raw)
    return {"label": label, "data": data, "sets_on": sets_on, "setup": setup, "was": snapshot(data),
            "was_full": {s["bucket"]: s["full_system"] for s in data["systems"]}, "was_sets": list(sets_on)}


def target_changes(t):
    """(added, removed) as {label: [text]} for a target; (new card's setup counts as a change on its own)."""
    now = snapshot(t["data"])
    added = {e: sorted(now[e] - t["was"][e]) for e in now if now[e] - t["was"][e]}
    removed = {e: sorted(t["was"][e] - now[e]) for e in now if t["was"][e] - now[e]}
    for s in t["data"]["systems"]:
        if s["full_system"] != t["was_full"][s["bucket"]]:
            (added if s["full_system"] else removed)[s["bucket"]] = ["(full system)"]
    on, was = set(t["sets_on"]), set(t["was_sets"])
    if on - was:
        added[SETS_KEY] = sorted(on - was)
    if was - on:
        removed[SETS_KEY] = sorted(was - on)
    return added, removed


def edit_manifest():
    """Add/remove games in the core list or a card's extras (browsing by system or by set), then save them."""
    print(bold("✏️  Edit mode") + dim(f"  read={PROFILE}"))
    manifest = load_manifest()  # also seeds games.json
    core_raw = personal_json("games.json")
    repo_systems = repo_json("systems")
    print(dim(f"📡 Listing s3://{BUCKET}/ ..."))
    with ThreadPoolExecutor(WORKERS) as ex:
        listings = ex.map(lambda s: {k for k in list_sizes(s["bucket"] + "/") if not k.endswith("/")}, repo_systems)
        bucket_keys = {s["bucket"]: keys for s, keys in zip(repo_systems, listings)}
    names = {s["bucket"] for s in repo_systems}
    sets = load_sets()
    sets_by_id = {x["id"]: x for x in sets}

    for game_set in sets:
        for g in game_set["games"]:
            if g.get("system") not in names:
                print(yellow(f"⚠️  Set {game_set['name']}: unknown system {g.get('system')!r}, skipped"), file=sys.stderr)

    targets = {}  # None (the core list) or a card name -> editing state

    def core_now():
        """The core list as it stands in this session."""
        core = targets.get(None)
        return dump_list(core["data"]["systems"], core["sets_on"]) if core else core_raw

    def edit_target(t, is_card):
        systems_all = t["data"]["systems"]
        by_bucket = {s["bucket"]: s for s in systems_all}
        systems = sorted((s for s in systems_all if bucket_keys[s["bucket"]]), key=lambda s: s["name"].lower())
        where = "games.json" if not is_card else f"{t['label']}'s extras"
        pos = {"system": 0, "set": 0}

        def cover():
            return cover_notes(sets_by_id, t["sets_on"], core_now() if is_card else None)

        def edit_system():
            now = snapshot(t["data"])
            full, keys = cover()
            width = max((len(s["name"]) for s in systems), default=0)
            labels, extras = [], []
            for s in systems:
                b = s["bucket"]
                changed = now[b] ^ t["was"][b]
                total = len(bucket_keys[b])
                whole = s.get("full_system") or b in full
                covered = {k for k in keys if k.split("/", 1)[0] == b}
                have = total if whole else len((now[b] | covered) & bucket_keys[b])
                missing = 0 if whole else len(now[b] - bucket_keys[b])
                labels.append(s["name"].ljust(width))
                row = [(f"  {have}", "green"), (f" / {total}", "dim")]
                if whole:
                    row.append(("  🗂️  full system", "cyan"))
                if missing:
                    row.append((f"  {missing} not in bucket", "red"))
                if changed:
                    row.append((f"  {len(changed)} change(s)", "cyan"))
                extras.append(row)
            i = filter_list("✏️  Pick a system to edit (Esc = back)", labels, extras=extras,
                            hint=FULL_HINT.format(what="full system"), cursor=pos["system"], hotkeys=(FULL_KEY,))
            if i is None:
                return False
            if isinstance(i, tuple):
                pos["system"] = i[1]
                s = systems[i[1]]
                if s["bucket"] in full:
                    print(yellow(f"ℹ️  {s['name']} is a full system in core, so it can't be changed here."))
                else:
                    toggle_full_system(s)
                return True
            pos["system"] = i
            s = systems[i]
            if s.get("full_system") or s["bucket"] in full:
                print(yellow(f"ℹ️  {s['name']} is a full system: every file in its bucket folder is "
                             "downloaded, so there is no game list to edit."))
                return True
            in_bucket = bucket_keys[s["bucket"]]
            listed = {g["bucket"] for g in s["games"] if g.get("bucket")}
            rows = [(s, k, os.path.splitext(k.split("/", 1)[1])[0],
                     k.split("/", 1)[1] + ("" if k in in_bucket else "  ⚠️ not in bucket"))
                    for k in sorted(in_bucket | listed, key=str.lower)]
            toggle_games(f"✏️  {s['name']} — ✅ in {where}, ⬜ in bucket only", rows,
                         covered=lambda _s, key: keys.get(key))
            return True

        def edit_set():
            if not sets:
                print(yellow("ℹ️  No game sets found."))
                return False
            full, keys = cover()
            labels, extras = [], []
            for game_set in sets:
                entries = [(g.get("system"), g.get("bucket")) for g in game_set["games"]]
                on = sum(1 for sid, key in entries if sid in by_bucket and (by_bucket[sid].get("full_system")
                         or any(g.get("bucket") == key for g in by_bucket[sid]["games"])
                         or sid in full or key in keys))
                desc = f" — {game_set['description']}" if game_set["description"] else ""
                labels.append(f"{game_set['name']}  ({on}/{len(entries)} on){desc}")
                extras.append([("  📦 full set", "green")] if game_set["id"] in t["sets_on"] else [])
            i = filter_list("✏️  Pick a set to edit (Esc = back)", labels, extras=extras,
                            hint=FULL_HINT.format(what="full set"), cursor=pos["set"], hotkeys=(FULL_KEY,))
            if i is None:
                return False
            if isinstance(i, tuple):
                pos["set"] = i[1]
                t["sets_on"] = toggle_set_ref(t["sets_on"], sets[i[1]]["id"])
                return True
            pos["set"] = i
            rows = set_rows(sets[i], by_bucket, lambda s: bucket_keys[s["bucket"]])
            if rows:
                files = {g["bucket"]: g["files"] for g in sets[i]["games"] if g.get("bucket") and g.get("files")}
                toggle_games(f"✏️  {sets[i]['name']} — ✅ in {where}, ⬜ not", rows, files,
                             covered=lambda s, key: full.get(s["bucket"]) or keys.get(key))
            else:
                print(yellow(f"ℹ️  {sets[i]['name']} has no games to toggle."))
            return True

        while True:
            i = filter_list(f"✏️  Edit {t['label']} (Esc = back)", ["By system", "By set"])
            if i is None:
                break
            while (edit_system, edit_set)[i]():
                pass

    def open_target(key, label, is_card):
        if key not in targets:
            raw = core_raw if key is None else card_games(key)
            targets[key] = new_target(label, raw)
        edit_target(targets[key], is_card)

    def add_card():
        existing = set(load_cards()) | set(targets)
        while True:
            name = input("➕ New card name (its folder name, empty to cancel): ").strip()
            if not name:
                return
            problem = valid_card_name(name, existing)
            if not problem:
                break
            print(yellow(f"  {problem}"))
        try:
            setup = choose_setup(manifest)
        except SystemExit:
            return
        targets[name] = new_target(name, {}, setup)
        edit_target(targets[name], True)

    while True:
        cards = sorted(set(load_cards()) | {k for k in targets if k is not None})
        options = ["🏠 Core (every card)"] + [f"💳 {name}" for name in cards] + ["➕ New card"]
        i = filter_list("✏️  What do you want to edit? (Esc = finish)", options)
        if i is None:
            break
        if i == 0:
            open_target(None, "🏠 Core", False)
        elif i == len(options) - 1:
            add_card()
        else:
            open_target(cards[i - 1], f"💳 {cards[i - 1]}", True)

    changed = {k: t for k, t in targets.items() if t["setup"] or any(target_changes(t))}
    if not changed:
        print(yellow("👋 No changes, nothing saved."))
        return 0
    print(bold("\n📝 Changes"))
    for t in changed.values():
        added, removed = target_changes(t)
        print(bold(f"  {t['label']}") + (dim("  (new card)") if t["setup"] else ""))
        for label, group, sign, col in (("added", added, "➕", green), ("removed", removed, "➖", red)):
            for esde, ks in group.items():
                print(col(f"  {sign} {esde}: {len(ks)} {label}"))
                for k in ks[:MAX_MISSING_SHOWN]:
                    print(dim(f"       {k.split('/', 1)[1] if '/' in k else k}"))
                if len(ks) > MAX_MISSING_SHOWN:
                    print(dim(f"       … and {len(ks) - MAX_MISSING_SHOWN} more"))
    print(dim("  (Removing only drops a game from the list; the file stays in the bucket.)"))

    if not confirm("💾 Save these changes?"):
        print(yellow("👋 Not saved."))
        return 0
    for key, t in changed.items():
        if t["setup"]:
            save_card(key, *t["setup"])
    save_lists(dump_list(targets[None]["data"]["systems"], targets[None]["sets_on"]) if None in changed else None,
               {k: dump_list(t["data"]["systems"], t["sets_on"]) for k, t in changed.items() if k is not None})
    print(green("🎉 Saved"))
    return 0


def rom_rel(key, flat):
    """A ROM's path inside its system folder: the bucket key without its system, or just the file name if flat."""
    rel = key.split("/", 1)[1]
    return os.path.basename(rel) if flat else rel


def archive_extracted(path):
    """Whether an archive's ROM is already beside it: a file with the archive's name and another extension."""
    stem, ext = os.path.splitext(os.path.basename(path))
    folder = os.path.dirname(path)
    if ext.lower() not in ARCHIVE_EXTS or not os.path.isdir(folder):
        return False
    return any(os.path.splitext(f)[0] == stem and not f.lower().endswith(ARCHIVE_EXTS) for f in os.listdir(folder))


def plan_downloads(jobs, unzip=False):
    """jobs: list of (s3_key, local_path, expected_size). Drops files already present, and with unzip the
    archives whose ROM was already extracted."""
    return [(k, p, s) for k, p, s in jobs
            if not (s is not None and os.path.exists(p) and os.path.getsize(p) == s)
            and not (unzip and archive_extracted(p))]


_s3 = {}


def s3_client(profile=None, connections=WORKERS):
    """Shared boto3 S3 client for a profile (one per connection pool size). Exits if the profile isn't configured."""
    profile = profile or PROFILE
    key = profile if connections == WORKERS else (profile, connections)
    if key not in _s3:
        try:
            session = boto3.Session(profile_name=profile)
        except ProfileNotFound:
            raise SystemExit(red(f"❌ AWS profile '{profile}' not found; define it in ~/.aws/config and ~/.aws/credentials"))
        config = Config(max_pool_connections=connections, **({"s3": {"addressing_style": "path"}} if ENDPOINT else {}))
        _s3[key] = session.client("s3", endpoint_url=ENDPOINT, config=config)
    return _s3[key]


def download(job, callback=None):
    """callback(bytes) is called as data arrives (not for a mirror copy, which finishes in one step)."""
    key, path, _ = job
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if _mirror_root:
        shutil.copyfile(os.path.join(_mirror_root, key), path + ".part")
        os.replace(path + ".part", path)
        return
    s3_client().download_file(BUCKET, key, path, Callback=callback)


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class ProgressBar:
    """One line under the log: say() prints a line above it, draw() refreshes it. Does nothing but print on a non-tty."""
    def __init__(self, count, fraction, total_bytes=None):
        self.count, self.fraction = count, fraction  # fraction() is the 0-1 progress of the whole run
        self.of = f" of {human_size(total_bytes)}" if total_bytes else ""  # the bar is by size, the count is by file
        self.shown = sys.stdout.isatty()

    def say(self, line):
        print(("\r\033[K" if self.shown else "") + line)

    def draw(self, done):
        if self.shown:
            fraction = self.fraction()
            filled = int(fraction * 24)
            sys.stdout.write(f"\r\033[K  {cyan('█' * filled)}{dim('░' * (24 - filled))} {done}/{self.count} files done  {fraction:4.0%}{self.of}")
            sys.stdout.flush()

    def clear(self):
        if self.shown:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()


class ByteProgress:
    """Bytes moved per job (weighted by size, at least 1 so empty files count); fraction() is the overall 0-1."""
    def __init__(self, sizes):
        self.size = [max(1, s or 0) for s in sizes]
        self.moved = [0] * len(sizes)
        self.lock = threading.Lock()

    def add(self, i, n):
        with self.lock:
            self.moved[i] = min(self.size[i], self.moved[i] + n)

    def finish(self, i):
        with self.lock:
            self.moved[i] = self.size[i]

    def fraction(self):
        return sum(self.moved) / sum(self.size)


def run_downloads(todo, label, icon, base):
    if not todo:
        print(green(f"{icon} {label}: nothing to download ✨"))
        return 0
    print(bold(f"\n{icon} {label}: downloading {len(todo)} file(s)"))
    failed = 0
    ex = ThreadPoolExecutor(WORKERS)
    moved = ByteProgress([j[2] for j in todo])
    bar = ProgressBar(len(todo), moved.fraction, sum(moved.size))
    try:
        futs = [(j, ex.submit(download, j, lambda n, i=i: moved.add(i, n))) for i, j in enumerate(todo)]
        for i, (j, f) in enumerate(futs, 1):
            prog = dim(f"[{i}/{len(todo)}]")
            try:
                while True:
                    try:
                        f.result(timeout=0.25)
                        break
                    except FutureTimeout:
                        bar.draw(i - 1)
                moved.finish(i - 1)
                src = j[0].split("/", 1)[0]
                rel = os.path.relpath(j[1], base)
                shown = j[0] if rel.split(os.sep, 1)[0] == src else f"{src} → {rel}"
                bar.say(f"  {prog} ✅ {shown}")
            except Exception as e:
                failed += 1
                moved.finish(i - 1)
                bar.say(f"  {prog} ❌ {red(j[0])}: {(getattr(e, 'stderr', None) or str(e)).strip()}")
            bar.draw(i)
    except KeyboardInterrupt:
        bar.say(yellow("🛑 Interrupted — dropping queued downloads, finishing the ones in flight..."))
        raise
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
        bar.clear()
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
# Dotfiles/folders that are OS litter; walk_roms(keep_dotfiles=True) drops only these (and "._*" AppleDouble files).
SYSTEM_DOT_NAMES = {".ds_store", ".localized", ".nomedia", ".appledouble", ".spotlight-v100", ".trashes",
                    ".fseventsd", ".temporaryitems", ".documentrevisions-v100", ".volumeicon.icns"}


def walk_roms(dest, keep_dotfiles=False):
    """os.walk over dest that yields only real ROM-folder content (no frontend/OS leftovers).

    keep_dotfiles: keep dotfiles that are real content, dropping only OS litter (.DS_Store, ._*, ...).
    """
    def hidden(name):
        if not name.startswith("."):
            return False
        return not keep_dotfiles or name.lower() in SYSTEM_DOT_NAMES or name.startswith("._")

    for root, dirs, files in os.walk(dest):
        at_root = os.path.normpath(root) == os.path.normpath(dest)
        dirs[:] = [d for d in dirs
                   if not hidden(d) and not (at_root and d.lower() in IGNORED_ROOT_DIRS)]
        files = [f for f in files
                 if not hidden(f) and f.lower() not in IGNORED_FILES
                 and not (at_root and f.lower() in IGNORED_ROOT_FILES)]
        yield root, files


def has_local_files(dest):
    """True if dest has any ROM file (frontend files and dotfiles are ignored)."""
    return any(files for _, files in walk_roms(dest))


def find_extras(dest, wanted_keys, unzip=False):
    """Local files under dest that aren't in the system's ROM list (frontend files and dotfiles are ignored).

    unzip: the layout extracts archives flat, so a listed archive's extracted ROM isn't an extra.
    """
    rels = [rom_rel(k, unzip) for k in wanted_keys]
    expected = {os.path.normpath(r) for r in rels}
    stems = {os.path.splitext(r)[0] for r in rels if r.lower().endswith(ARCHIVE_EXTS)} if unzip else set()
    extras = []
    for root, files in walk_roms(dest):
        for f in files:
            path = os.path.join(root, f)
            rel = os.path.normpath(os.path.relpath(path, dest))
            if rel not in expected and os.path.splitext(rel)[0] not in stems:
                extras.append(path)
    return extras


DISC_RE = re.compile(r" \(Disc (\d+)\)")
DISC_EXTS = {".chd", ".cue", ".iso", ".pbp", ".gdi", ".cso", ".ccd"}


def disc_groups(files):
    """{m3u name: disc files in order} for the multi-disc games among one folder's files.

    "Name (Disc 1) (Key Disc) (Sega CD).chd" and "Name (Disc 2) (Sega CD).chd" are one game; the playlist is named
    after the title with "(Disc N)" and any tags the discs don't all share removed: "Name (Sega CD).m3u".
    """
    games = defaultdict(list)
    for f in files:
        stem, ext = os.path.splitext(f)
        m = DISC_RE.search(stem)
        if m and ext.lower() in DISC_EXTS:
            games[(stem[:m.start()], ext.lower())].append((int(m.group(1)), re.findall(r"\([^)]*\)", stem[m.end():]), f))
    groups = {}
    for (title, _), discs in games.items():
        discs.sort()
        if len(discs) < 2 or len({n for n, _, _ in discs}) < len(discs):
            continue
        shared = [t for t in discs[0][1] if all(t in tags for _, tags, _ in discs)]
        groups[title + "".join(f" {t}" for t in shared) + ".m3u"] = [f for _, _, f in discs]
    return groups


def m3u_entries(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return [line.strip() for line in f if line.strip() and not line.lstrip().startswith("#")]


def plan_m3u(root):
    """[(action, path, lines)] to make every multi-disc game under root have a correct .m3u.

    create: a game with none. rewrite: a playlist whose discs differ from the game's, or one with some missing files.
    delete: a playlist whose files are all missing. rename: a playlist under another name that lists exactly a game's
    discs (lines is the new path). A playlist that matches no game is kept if all its files exist.
    """
    plan = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        files = sorted(f for f in files if not f.startswith("."))
        groups = disc_groups(files)
        covered = {}
        for f in files:
            if not f.lower().endswith(".m3u") or f in groups:
                continue
            path = os.path.join(dirpath, f)
            entries = m3u_entries(path)
            valid = [e for e in entries if os.path.exists(os.path.join(dirpath, e))]
            if not valid:
                plan.append(("delete", path, []))
            elif len(valid) < len(entries):
                plan.append(("rewrite", path, valid))
            covered.setdefault(tuple(sorted(valid)), path)
        for name, discs in groups.items():
            path = os.path.join(dirpath, name)
            if name in files:
                if m3u_entries(path) != discs:
                    plan.append(("rewrite", path, discs))
            elif tuple(sorted(discs)) in covered:
                plan.append(("rename", covered[tuple(sorted(discs))], path))
            else:
                plan.append(("create", path, discs))
    return plan


def m3u_command(args):
    root = os.path.abspath(os.path.expanduser(args.m3u or os.getcwd()))
    if not os.path.isdir(root):
        raise SystemExit(red(f"❌ {root} is not a folder"))
    print(bold("💿 m3u playlists") + dim(f"  {root}"))
    plan = plan_m3u(root)
    if not plan:
        print(green("✅ All multi-disc playlists are correct"))
        return 0
    icons = {"create": "➕", "rewrite": "✏️ ", "delete": "🗑️ ", "rename": "🏷️ "}
    for action, path, lines in plan:
        to = f" {dim('→')} {os.path.basename(lines)}" if action == "rename" else ""
        print(f"  {icons[action]} {action} {os.path.relpath(path, root)}{to}")
    if args.dry_run:
        print(yellow("\n🧪 Dry run — nothing changed"))
        return 0
    deletes = [path for action, path, _ in plan if action == "delete"]
    kept = 0
    if deletes and not confirm(f"🗑️  Delete {len(deletes)} playlist(s) whose files are all missing?", default=False):
        print(yellow("  ↩️  Keeping them"))
        kept, deletes = len(deletes), []
    for action, path, lines in plan:
        if action == "delete":
            if path in deletes:
                os.remove(path)
        elif action == "rename":
            os.rename(path, lines)
        else:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("".join(line + "\n" for line in lines))
    print(green(f"🎉 Done: {len(plan) - kept} change(s)"))
    return 0


ARCHIVE_EXTS = (".zip", ".7z")
SHEET_EXTS = (".cue", ".gdi", ".toc")  # chdman reads these; the sheet names the track files
TOOL_FORMULAE = {"7z": "sevenzip", "chdman": "rom-tools"}  # Homebrew formula that provides each tool
TOOL_NAMES = {"7z": ("7zz", "7z", "7za"), "chdman": ("chdman",)}


def find_tool(tool):
    return next((p for p in map(shutil.which, TOOL_NAMES[tool]) if p), None)


def chd_folders(systems):
    """{lowercase folder name: system} for the systems with a chd setting, over every layout's folder name."""
    return {f.lower(): s for s in systems if s.get("chd") for f in s["folders"].values() if f}


def sheet_tracks(path):
    """Names of the track files a .cue/.gdi/.toc sheet points at."""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if path.lower().endswith(".gdi"):
        names = re.findall(r'^[ \t]*\d+[ \t]+\d+[ \t]+\d+[ \t]+\d+[ \t]+("[^"]+"|\S+)', text, re.M)
        return [n.strip('"') for n in names]
    return re.findall(r'(?:FILE|DATAFILE|AUDIOFILE)\s+"([^"]+)"', text, re.I)


def disc_images(paths):
    """[(image, files it owns)]: each cue/gdi/toc sheet with its tracks, then each .iso no sheet uses."""
    images, used = [], set()
    for p in sorted(paths):
        if p.lower().endswith(SHEET_EXTS):
            tracks = [os.path.join(os.path.dirname(p), t) for t in sheet_tracks(p)]
            images.append((p, [p] + tracks))
            used.update(tracks)
    return images + [(p, [p]) for p in sorted(paths) if p.lower().endswith(".iso") and p not in used]


def chd_system(root, dirpath, folders):
    """(system, its outermost folder) for a folder under root: the first path part that names a chd system."""
    rel = os.path.relpath(dirpath, root)
    path = os.path.dirname(root)
    for part in [os.path.basename(root)] + ([] if rel == "." else rel.split(os.sep)):
        path = os.path.join(path, part)
        if part.lower() in folders:
            return folders[part.lower()], path
    return None, None


def plan_chd(root, folders):
    """[(system, system folder, file, owned)] to convert under root: owned is None for an archive, else the
    loose disc image's files (sheet and tracks, or the iso). Extract-only systems have archives only."""
    jobs = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        system, sysroot = chd_system(root, dirpath, folders)
        if not system:
            continue
        files = [os.path.join(dirpath, f) for f in sorted(files) if not f.startswith(".")]
        jobs += [(system, sysroot, f, None) for f in files if f.lower().endswith(ARCHIVE_EXTS)]
        if system["chd"]["mode"] != "extract":
            jobs += [(system, sysroot, img, owned) for img, owned in disc_images(files)]
    return jobs


_tool_procs = set()  # running tools, so an interrupt can stop them
_tool_lock = threading.Lock()
_tools_stopped = False


def stop_tools():
    """Terminate the running tools; run_tool starts no new ones afterwards."""
    global _tools_stopped
    with _tool_lock:
        _tools_stopped = True
        for proc in _tool_procs:
            proc.terminate()


PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)% complete")


def run_tool(cmd, progress=None):
    """None on success, else the last line the tool printed; progress(percent) is called as chdman reports it."""
    with _tool_lock:
        if _tools_stopped:
            return "interrupted"
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        _tool_procs.add(proc)
    last = ""
    try:
        for line in proc.stderr:  # chdman ends its progress updates with \r, which text mode reads as a line end
            match = PERCENT_RE.search(line)
            if match and progress:
                progress(float(match.group(1)))
            elif line.strip():
                last = line.strip()
        proc.wait()
    finally:
        with _tool_lock:
            _tool_procs.discard(proc)
    if proc.returncode:
        return last or f"exit code {proc.returncode}"


def chd_command_line(chdman, cfg, image, out, np):
    dvd = cfg["mode"] == "dvd" and image.lower().endswith(".iso")
    return [chdman, "createdvd" if dvd else "createcd", "-i", image, "-o", out, "-np", str(np)] + (cfg.get("args", []) if dvd else [])


_chd_locks = defaultdict(threading.Lock)  # one per output path: two jobs for the same disc take turns


def make_chd(tools, cfg, image, out, report=None):
    """Create out from image (an existing out is only verified); None on success, else the error.

    The chd is built under a hidden .part name and renamed once it verifies, so out is never half written.
    report(fraction) gets 0-1 progress: creating is the first 90%, verifying the last 10%.
    """
    chdman = tools["chdman"]

    def stage(start, width):
        return (lambda percent: report(start + percent / 100 * width)) if report else None

    part = os.path.join(os.path.dirname(out), "." + os.path.basename(out) + ".part")
    with _chd_locks[out]:
        if os.path.exists(out):
            return run_tool([chdman, "verify", "-i", out], stage(0, 1))
        if os.path.exists(part):  # left by a run that was killed
            os.remove(part)
        error = (run_tool(chd_command_line(chdman, cfg, image, part, tools["np"]), stage(0, 0.9))
                 or run_tool([chdman, "verify", "-i", part], stage(0.9, 0.1)))
        if error:
            if os.path.exists(part):
                os.remove(part)
            return error
        os.replace(part, out)


def chd_archive(tools, cfg, path, report=None):
    """Extract an archive next to itself, then convert its discs (or, for extract-only systems, move its files out).
    The archive goes only once everything is done; None on success, else the error."""
    folder = os.path.dirname(path)
    tmp = tempfile.mkdtemp(prefix=".chd-", dir=folder)
    try:
        error = run_tool([tools["7z"], "x", "-y", "-bso0", "-bsp0", f"-o{tmp}", path])
        if error:
            return error
        extracted = [os.path.join(dp, f) for dp, _, fns in os.walk(tmp) for f in sorted(fns)]
        if cfg["mode"] == "extract":
            names = [os.path.join(folder, os.path.basename(f)) for f in extracted]
            clash = next((n for n in names if os.path.exists(n)), None)
            if clash:
                return f"{os.path.basename(clash)} already exists"
            for f, n in zip(extracted, names):
                shutil.move(f, n)
        else:
            images = disc_images(extracted)
            if not images:
                return "no disc image in the archive"
            for image, _ in images:
                error = make_chd(tools, cfg, image, os.path.join(folder, os.path.splitext(os.path.basename(image))[0] + ".chd"), report)
                if error:
                    return error
        os.remove(path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def chd_image(tools, cfg, image, owned, report=None):
    """Convert one loose disc image and remove its files once the chd verifies; None on success, else the error."""
    error = make_chd(tools, cfg, image, os.path.splitext(image)[0] + ".chd", report)
    if not error:
        for f in owned:
            if os.path.exists(f):
                os.remove(f)
    return error


def unzip_archive(path):
    """Extract an archive's files next to it, without subfolders, and delete it. None on success, else the error."""
    folder = os.path.dirname(path)
    tmp = tempfile.mkdtemp(prefix=".unzip-", dir=folder)
    try:
        if path.lower().endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                z.extractall(tmp)
        else:
            tool = next((t for name in TOOL_NAMES["7z"] for t in [shutil.which(name)] if t), None)
            if not tool:
                return "needs 7z to extract (see --install-tools)"
            error = run_tool([tool, "x", "-y", "-bso0", "-bsp0", f"-o{tmp}", path])
            if error:
                return error
        for dirpath, _, names in os.walk(tmp):
            for name in sorted(names):
                shutil.move(os.path.join(dirpath, name), os.path.join(folder, name))
        os.remove(path)
    except (OSError, zipfile.BadZipFile) as e:
        return str(e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def unzip_roms(paths):
    """Extract the archives among the downloaded paths. Returns [(path, error)] for the ones that failed."""
    failures = []
    for path in paths:
        if path.lower().endswith(ARCHIVE_EXTS) and os.path.exists(path):
            error = unzip_archive(path)
            if error:
                failures.append((path, error))
    return failures


def remove_stale_chd_temp(root):
    """Delete the .chd-* extraction folders a killed run left behind."""
    for dirpath, dirs, _ in os.walk(root):
        for d in [d for d in dirs if d.startswith(".chd-")]:
            shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)
            dirs.remove(d)


def chd_roots(root, folders):
    """{system folder: system} for every system folder under root: where the m3u playlists get fixed."""
    roots = {}
    for dirpath, dirs, _ in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        system, sysroot = chd_system(root, dirpath, folders)
        if system:
            roots[sysroot] = system
    return roots


def fix_playlists(roots, dry_run):
    """Run the --m3u pass on each system folder that has playlists."""
    for sysroot, system in roots.items():
        if system["chd"]["mode"] != "extract" and system["chd"].get("m3u", True):
            m3u_command(SimpleNamespace(m3u=sysroot, dry_run=dry_run))


def chd_command(args):
    root = os.path.abspath(os.path.expanduser(args.chd or os.getcwd()))
    if not os.path.isdir(root):
        raise SystemExit(red(f"❌ {root} is not a folder"))
    print(bold("💿 chd") + dim(f"  {root}"))
    folders = chd_folders(repo_json("systems"))
    roots = chd_roots(root, folders)
    jobs = plan_chd(root, folders)
    if not jobs:
        print(green("✅ Nothing to convert"))
        if not roots:
            print(yellow("⚠️  No folder here is named after a system with a chd setting, so every file was skipped."))
            print(dim(f"   --chd only looks inside folders named: {', '.join(sorted(folders))}"))
    for system, _, path, owned in jobs:
        what = "extract" if system["chd"]["mode"] == "extract" else "convert"
        print(f"  {'📦' if owned is None else '💿'} {what} {os.path.relpath(path, root)}")
    if args.dry_run:
        fix_playlists(roots, True)
        print(yellow("\n🧪 Dry run — nothing changed"))
        return 0
    if not jobs:
        fix_playlists(roots, False)
        return 0
    tools = {}
    for tool, needed in (("7z", any(j[3] is None for j in jobs)), ("chdman", any(j[0]["chd"]["mode"] != "extract" for j in jobs))):
        tools[tool] = find_tool(tool)
        if needed and not tools[tool]:
            raise SystemExit(red(f"❌ {tool} not found; run sync-roms --install-tools"))
    remove_stale_chd_temp(root)
    cpus = os.cpu_count() or 1
    workers = min(cpus, len(jobs))
    tools["np"] = max(1, cpus // workers)  # cores left for each chdman once the jobs share them
    print(dim(f"  {workers} at a time, {tools['np']} core(s) each"))

    progress = [0.0] * len(jobs)  # each job's 0-1 progress; the bar is their mean

    def convert(i):
        system, _, path, owned = jobs[i]

        def report(fraction):
            progress[i] = max(progress[i], fraction)

        try:
            if owned:
                return chd_image(tools, system["chd"], path, owned, report)
            return chd_archive(tools, system["chd"], path, report)
        finally:
            progress[i] = 1.0

    bar = ProgressBar(len(jobs), lambda: sum(progress) / len(jobs))
    say = bar.say

    def draw_bar():
        bar.draw(sum(1 for p in progress if p >= 1))

    converted, failed = 0, 0
    pool = ThreadPoolExecutor(workers)
    futures = [pool.submit(convert, i) for i in range(len(jobs))]
    try:
        for job, future in zip(jobs, futures):
            while True:
                try:
                    error = future.result(timeout=0.25)
                    break
                except FutureTimeout:
                    draw_bar()
            name = os.path.relpath(job[2], root)
            if error:
                failed += 1
                say(red(f"  ❌ {name}: {error}") + dim(" (kept)"))
            else:
                converted += 1
                say(f"  ✅ {name}")
            draw_bar()
    except KeyboardInterrupt:
        say(yellow("🛑 Interrupted, stopping and cleaning up..."))
        for future in futures:
            future.cancel()
        while True:  # the running jobs remove their partial files as the tools stop
            stop_tools()
            try:
                pool.shutdown(wait=True)
                break
            except KeyboardInterrupt:
                pass
        print(yellow(f"  {converted} done, nothing half-converted; run --chd again to continue"))
        return 130
    pool.shutdown()
    bar.clear()
    fix_playlists(roots, False)
    print((red if failed else green)(f"🎉 Done: {converted} converted, {failed} failed"))
    return 1 if failed else 0


def install_tools_command():
    brew = shutil.which("brew")
    if not brew:
        raise SystemExit(red("❌ Homebrew (brew) not found; install it from https://brew.sh"))
    wanted = [formula for tool, formula in TOOL_FORMULAE.items() if not find_tool(tool)]
    if not wanted:
        print(green("✅ 7z and chdman are already installed"))
        return 0
    print(bold("🍺 brew install ") + " ".join(wanted))
    return subprocess.run([brew, "install", *wanted]).returncode


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
# Slot's cart labels are made the same way (PNG fitting the cart's label size), by system, stored as
# scrapes/<system>/slot/<ROM name>.png.
SLOT_TYPE = "slot"
SLOT_ART = ("covers", "3dboxes", "screenshots")
SLOT_LABEL_MAX = {"gba": (1280, 661), "gb": (1024, 914), "gbc": (1024, 914)}
BUCKET_MEDIA = MEDIA_TYPES | {ONION_TYPE, SLOT_TYPE}
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
    return s3_client().get_object(Bucket=BUCKET, Key=key)["Body"].read().decode("utf-8")


def fetch_texts(keys):
    keys = sorted(keys)
    with ThreadPoolExecutor(WORKERS) as ex:
        return dict(zip(keys, ex.map(get_text, keys)))


def put_text(key, text):
    s3_client(WRITE_PROFILE).put_object(Bucket=BUCKET, Key=key, Body=text.encode("utf-8"))


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
    art = defaultdict(dict)  # (system, ROM name) -> {media type: local path} for Onion box art and Slot labels
    for system in sorted(os.listdir(media)) if os.path.isdir(media) else []:
        if not stems.get(system):
            continue
        for mtype in sorted(MEDIA_TYPES):
            base = os.path.join(media, system, mtype)
            for rel, full in walk_files(base) if os.path.isdir(base) else []:
                stem = os.path.splitext(rel)[0]
                if stem in stems[system]:
                    want_file(f"{SCRAPES}/{system}/{mtype}/{rel}", full)
                    if mtype in ONION_ART + SLOT_ART:
                        art[(system, stem)][mtype] = full
    for (system, stem), found in sorted(art.items()):
        wanted = [(ONION_TYPE, ONION_ART, ONION_MAX)] if "/" not in stem else []  # Onion's Imgs folder is flat
        if system in SLOT_LABEL_MAX:
            wanted.append((SLOT_TYPE, SLOT_ART, SLOT_LABEL_MAX[system]))
        for kind, order, box in wanted:
            key = f"{SCRAPES}/{system}/{kind}/{stem}.png"
            source = next((found[t] for t in order if t in found), None)
            if key in existing:
                plan["derived_present"] += 1
            elif source:
                plan["derived"].append((key, source, os.path.getsize(source), box))

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
        manifest = load_manifest([os.path.basename(base) or base])
        print("📏 Listing the ROMs available in the bucket...")
        roms = bucket_roms(manifest["systems"])
        print("☁️  Listing what's already in scrapes/...")
        existing = list_sizes(SCRAPES + "/")
        remote_texts = fetch_texts(text_keys(existing))
        print("🔎 Comparing...")
        plan = plan_upload(es_dir, roms, existing, remote_texts)
    except (ClientError, BotoCoreError) as e:
        raise SystemExit(red(f"❌ {e}"))
    for w in plan["warnings"]:
        print(yellow(f"  ⚠️  {w}"))
    files, texts, derived = plan["files"], plan["texts"], plan["derived"]
    if derived and not can_shrink():
        print(yellow(f"  ⚠️  Onion box art and Slot labels need Pillow or macOS sips to resize images; skipping {len(derived)} file(s)"))
        derived = []
    print(f"\n📝 Text files to write: {bold(str(len(texts)))}")
    for _, _, label in texts[:15]:
        print(dim(f"     {label}"))
    if len(texts) > 15:
        print(dim(f"     … and {len(texts) - 15} more"))
    print(f"🖼️  Files to upload (media, themes): {bold(str(len(files)))} "
          f"({human_size(sum(f[2] for f in files))}), {plan['present']} already there")
    print(f"🧅 Onion box art and Slot labels to create from local images: {bold(str(len(derived)))}, {plan['derived_present']} already there")
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
    with ThreadPoolExecutor(WORKERS) as ex:
        for label, f in [(label, ex.submit(put_text, key, text)) for key, text, label in texts]:
            try:
                f.result()
                print(f"  ✅ {label}")
            except Exception as e:
                failed += 1
                print(f"  ❌ {red(label)}: {(getattr(e, 'stderr', None) or str(e)).strip()}")
    failed += run_uploads(files + derived) if files or derived else 0
    print(green("\n🎉 Done!") if not failed else red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0


UPLOAD_MULTIPART_AT = 64 * 1024 * 1024  # files this big go up as parallel parts
UPLOAD_PART = 32 * 1024 * 1024


def upload_workers():
    """Requests in flight at once. Uploads wait on the network, not the CPU, so run several per core."""
    return min(64, 4 * (os.cpu_count() or 4))


def guess_system(systems, folder):
    """Index of the system whose bucket id (first) or frontend folder name is the folder's name, else None."""
    name = os.path.basename(os.path.normpath(folder)).lower()
    for i, s in enumerate(systems):
        if s["bucket"].lower() == name:
            return i
    for i, s in enumerate(systems):
        if name in (f.lower() for f in s["folders"].values() if f):
            return i
    return None


def plan_rom_upload(root, bucket, existing):
    """(new, changed, same) lists of (key, path, size) for the ROM files under root, keyed bucket/relative path.

    existing: {key: size} listing of the bucket folder; a file whose size matches is the same.
    """
    new, changed, same = [], [], []
    for dirpath, files in walk_roms(root, keep_dotfiles=True):
        for f in sorted(files):
            path = os.path.join(dirpath, f)
            key = f"{bucket}/{os.path.relpath(path, root).replace(os.sep, '/')}"
            size = os.path.getsize(path)
            if key not in existing:
                new.append((key, path, size))
            elif existing[key] == size:
                same.append((key, path, size))
            else:
                changed.append((key, path, size))
    return new, changed, same


class QueueWhenDone(BaseSubscriber):
    def __init__(self, done, job, moved=None):
        self.done, self.job, self.moved = done, job, moved  # moved(bytes) is called as parts go up

    def on_progress(self, future, bytes_transferred, **kwargs):
        if self.moved:
            self.moved(bytes_transferred)

    def on_done(self, future, **kwargs):
        self.done.put((self.job, future))


class FailedUpload:
    """Stands in for a finished transfer of a job that failed before it could be queued."""
    def __init__(self, error):
        self.error = error

    def result(self):
        raise self.error


def run_uploads(todo):
    """Upload (key, path, size[, shrink]) jobs through one shared pool of requests, so small files and the parts of
    big ones all keep the connection busy. Biggest files start first so a long one never trails at the end.
    A 4th element (max width, max height) means: upload path shrunk to fit it, shrunk on every core while the others upload."""
    workers = upload_workers()
    print(bold(f"\n☁️  Uploading {len(todo)} file(s)") + dim(f"  {workers} requests at once"))
    config = TransferConfig(max_concurrency=workers, multipart_threshold=UPLOAD_MULTIPART_AT,
                            multipart_chunksize=UPLOAD_PART)
    done, failed = queue.Queue(), 0
    order = sorted(todo, key=lambda j: -j[2])
    moved = ByteProgress([j[2] for j in order])
    bar = ProgressBar(len(todo), moved.fraction, sum(moved.size))
    try:
        with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(os.cpu_count() or 4) as shrinkers, \
                create_transfer_manager(s3_client(WRITE_PROFILE, connections=workers), config) as manager:
            def send(job, path, n):
                manager.upload(path, BUCKET, job[0],
                               {"ContentType": mimetypes.guess_type(path)[0] or "application/octet-stream"},
                               [QueueWhenDone(done, job, lambda b: moved.add(n, b))])

            def shrink_and_send(job, n):
                try:
                    art = os.path.join(tmp, f"{n}.png")
                    shrink_png(job[1], art, job[3])
                    send(job, art, n)
                except Exception as e:
                    done.put((job, FailedUpload(e)))

            try:
                def submit_all():  # queueing blocks once the transfer queue is full, so it can't hold up the output
                    for n, job in enumerate(order):
                        try:
                            if len(job) > 3:
                                shrinkers.submit(shrink_and_send, job, n)
                            else:
                                send(job, job[1], n)
                        except Exception as e:
                            done.put((job, FailedUpload(e)))

                index = {id(job): n for n, job in enumerate(order)}
                threading.Thread(target=submit_all, daemon=True).start()
                for i in range(1, len(todo) + 1):
                    while True:
                        try:
                            job, future = done.get(timeout=0.25)
                            break
                        except queue.Empty:
                            bar.draw(i - 1)
                    moved.finish(index[id(job)])
                    prog = dim(f"[{i}/{len(todo)}]")
                    try:
                        future.result()
                        bar.say(f"  {prog} ✅ {job[0]}")
                    except Exception as e:
                        failed += 1
                        bar.say(f"  {prog} ❌ {red(job[0])}: {str(e).strip()}")
                    bar.draw(i)
            except KeyboardInterrupt:
                shrinkers.shutdown(wait=False, cancel_futures=True)
                raise
    except KeyboardInterrupt:
        bar.say(yellow("🛑 Interrupted — dropping queued uploads, finishing the ones in flight..."))
        raise
    finally:
        bar.clear()
    return failed


def upload_command(args):
    """Upload the ROMs in one folder (default: the current directory) to the bucket folder of a system you pick."""
    folder = os.path.abspath(os.path.expanduser(args.upload or os.getcwd()))
    if not os.path.isdir(folder):
        raise SystemExit(red(f"❌ {folder} is not a folder"))
    systems = sorted(load_manifest()["systems"], key=lambda s: s["name"].lower())
    guess = guess_system(systems, folder)
    i = filter_list("☁️  Which system are you uploading?", [f"{s['name']}  ({s['bucket']}/)" for s in systems],
                    cursor=guess or 0, hint="type to filter · ↑/↓ move · Enter continue · Esc cancel")
    if i is None:
        print(yellow("👋 Cancelled."))
        return 0
    bucket = systems[i]["bucket"]
    print(bold(f"☁️  {'Replace' if args.replace else 'Upload'} {systems[i]['name']}") + dim(f"  read={PROFILE}  write={WRITE_PROFILE}  {folder} → s3://{BUCKET}/{bucket}/"))
    if args.replace:
        return replace_command(args, folder, systems[i])
    try:
        print("☁️  Listing what's already there...")
        existing = list_sizes(bucket + "/")
    except (ClientError, BotoCoreError) as e:
        raise SystemExit(red(f"❌ {e}"))
    new, changed, same = plan_rom_upload(folder, bucket, existing)
    print(f"\n💿 New: {bold(str(len(new)))} ({human_size(sum(f[2] for f in new))})")
    print(f"♻️  Different size, would overwrite: {bold(str(len(changed)))} ({human_size(sum(f[2] for f in changed))})")
    print(f"⚡ Already there: {len(same)}")
    todo = new + changed
    if not todo:
        print(green("Nothing to upload ✨"))
        return 0
    for key, _, size in changed[:10]:
        print(yellow(f"     overwrite {key} {dim(human_size(size))}"))
    if len(changed) > 10:
        print(yellow(f"     … and {len(changed) - 10} more"))
    if args.dry_run:
        print(yellow("\n🧪 Dry run — nothing uploaded"))
        for key, _, size in new[:20]:
            print(f"  {key} {dim(human_size(size))}")
        if len(new) > 20:
            print(dim(f"  … and {len(new) - 20} more"))
        return 0
    if not confirm(f"☁️  Upload {len(todo)} file(s) to s3://{BUCKET}/{bucket}/" + (f", overwriting {len(changed)}" if changed else "") + "?", default=False):
        print(yellow("👋 Cancelled."))
        return 0
    failed = run_uploads(todo)
    print(green("\n🎉 Done!") if not failed else red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0


class RangeReader(io.RawIOBase):
    """Read-only file over a bucket object, fetching byte ranges; the tail is cached since a zip's index is there."""
    TAIL = 65536

    def __init__(self, key, size):
        self.key, self.size, self.pos = key, size, 0
        self.tail_at = max(0, size - self.TAIL)
        self.tail = self.fetch(self.tail_at, size) if size else b""

    def fetch(self, start, end):
        if end <= start:
            return b""
        r = s3_client().get_object(Bucket=BUCKET, Key=self.key, Range=f"bytes={start}-{end - 1}")
        return r["Body"].read()

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, offset, whence=os.SEEK_SET):
        self.pos = offset if whence == os.SEEK_SET else self.pos + offset if whence == os.SEEK_CUR else self.size + offset
        return self.pos

    def read(self, n=-1):
        end = self.size if n is None or n < 0 else min(self.size, self.pos + n)
        if self.pos >= self.tail_at:
            data = self.tail[self.pos - self.tail_at:end - self.tail_at]
        else:
            data = self.fetch(self.pos, end)
        self.pos += len(data)
        return data


def zip_fingerprint(fileobj):
    """The (size, crc32) of every file inside a zip, from its index alone, so the name and compression don't matter."""
    with zipfile.ZipFile(fileobj) as z:
        return ("zip", tuple(sorted((i.file_size, i.CRC) for i in z.infolist() if not i.is_dir())))


def file_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def local_fingerprint(path):
    try:
        return zip_fingerprint(path)
    except zipfile.BadZipFile:
        return ("raw", os.path.getsize(path), file_md5(path))


def bucket_fingerprint(key, size, etag):
    try:
        return zip_fingerprint(RangeReader(key, size))
    except (zipfile.BadZipFile, ClientError, BotoCoreError):
        etag = etag.strip('"')
        return ("raw", size, None if "-" in etag else etag)  # a multipart upload's ETag isn't an md5


def same_content(a, b):
    if a[0] != b[0]:
        return False
    return a == b if a[0] == "zip" else a[1] == b[1] and (a[2] is None or b[2] is None or a[2] == b[2])


def list_with_etags(prefix):
    pages = s3_client().get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix)
    return {o["Key"][len(prefix):]: (o["Size"], o["ETag"]) for page in pages for o in page.get("Contents", [])
            if not o["Key"].endswith("/")}


def match_content(local, remote, local_print, remote_print, differs=None):
    """([(local path, bucket path)] with the same content, only local, only bucket) lists, ignoring names.

    local: {path: size}; remote: {path: (size, etag)}. A file with the same path and size on both sides is the same
    without reading it; the rest are matched by content, a file with the same path first. local_print(path) /
    remote_print(path, size, etag) return a fingerprint, and are only called for the files left over.
    differs(path, etag), if given, is asked about same-path same-size files and returns True when their bytes are
    known to differ; those are then matched by content too.
    """
    with ThreadPoolExecutor(WORKERS) as ex:
        same = [p for p, size in local.items() if p in remote and remote[p][0] == size]
        suspect = {p for p, d in zip(same, ex.map(lambda p: differs(p, remote[p][1]), same)) if d} if differs else set()
        left_local = sorted(p for p, size in local.items() if p not in remote or remote[p][0] != size or p in suspect)
        left_remote = sorted(p for p, (size, _) in remote.items() if p not in local or local[p] != size or p in suspect)
        local_prints = list(ex.map(local_print, left_local))
        remote_prints = list(ex.map(lambda p: remote_print(p, *remote[p]), left_remote))
    unmatched = list(zip(left_remote, remote_prints))
    matched, only_local = [], []
    for path, fp in zip(left_local, local_prints):
        candidates = sorted(range(len(unmatched)), key=lambda i: unmatched[i][0] != path)
        for i in candidates:
            if same_content(fp, unmatched[i][1]):
                matched.append((path, unmatched.pop(i)[0]))
                break
        else:
            only_local.append(path)
    return matched, only_local, [p for p, _ in unmatched]


def plan_diff(local, remote, local_print, remote_print):
    """(only local, only bucket) lists of relative paths, ignoring renames. Arguments as in match_content."""
    _, only_local, only_bucket = match_content(local, remote, local_print, remote_print)
    return only_local, only_bucket


def plan_replace(local, remote, local_print, remote_print, differs=None):
    """(renames, new, changed, only bucket) for making the bucket folder match the local one.

    renames: [(bucket path, local path)] with the same content under another name. changed: paths on both sides
    with different content. Arguments as in match_content.
    """
    matched, only_local, only_bucket = match_content(local, remote, local_print, remote_print, differs)
    renames = [(r, l) for l, r in matched if l != r]
    targets = {l for _, l in renames}
    changed = [p for p in only_local if p in remote]
    new = [p for p in only_local if p not in remote]
    # an unmatched bucket file under a rename's new name or a changed file's name is overwritten, not left behind
    only_bucket = [p for p in only_bucket if p not in targets and p not in local]
    return renames, new, changed, only_bucket


def local_sizes(folder):
    """{relative path: size} of the ROM files under folder."""
    sizes = {}
    for dirpath, files in walk_roms(folder, keep_dotfiles=True):
        for f in files:
            path = os.path.join(dirpath, f)
            sizes[os.path.relpath(path, folder).replace(os.sep, "/")] = os.path.getsize(path)
    return sizes


def move_keys(moves):
    """Move bucket objects server-side: copy each (old key, new key), then delete the old one. Returns the failure count."""
    client = s3_client(WRITE_PROFILE)

    def move(job):
        old, new = job
        try:
            client.copy({"Bucket": BUCKET, "Key": old}, BUCKET, new)
            client.delete_object(Bucket=BUCKET, Key=old)
            return job, None
        except (ClientError, BotoCoreError) as e:
            return job, e

    failed = 0
    print(bold(f"\n🚚 Moving {len(moves)} renamed file(s)"))
    with ThreadPoolExecutor(WORKERS) as ex:
        for i, (job, error) in enumerate(ex.map(move, moves), 1):
            prog = dim(f"[{i}/{len(moves)}]")
            if error is None:
                print(f"  {prog} ✅ {job[0]} → {job[1]}")
            else:
                failed += 1
                print(f"  {prog} ❌ {red(job[0])}: {str(error).strip()}")
    return failed


def replace_command(args, folder, system):
    """Make a bucket folder match a local one: move renamed files, upload new and changed ones, and delete the rest
    that you pick."""
    bucket = system["bucket"]
    local = local_sizes(folder)
    try:
        print("☁️  Listing what's already there...")
        remote = list_with_etags(bucket + "/")
        print("🔍 Matching files by content...")
        renames, new, changed, only_bucket = plan_replace(
            local, remote, lambda p: local_fingerprint(os.path.join(folder, *p.split("/"))),
            lambda p, size, etag: bucket_fingerprint(f"{bucket}/{p}", size, etag),
            lambda p, etag: "-" not in etag and file_md5(os.path.join(folder, *p.split("/"))) != etag.strip('"'))
    except (ClientError, BotoCoreError) as e:
        raise SystemExit(red(f"❌ {e}"))
    print(f"\n💿 New: {bold(str(len(new)))} ({human_size(sum(local[p] for p in new))})")
    print(f"♻️  Different content, would overwrite: {bold(str(len(changed)))} ({human_size(sum(local[p] for p in changed))})")
    print(f"🚚 Renamed, would move in the bucket: {bold(str(len(renames)))}")
    print(f"🗑️  Only in the bucket, not renames: {bold(str(len(only_bucket)))} ({human_size(sum(remote[p][0] for p in only_bucket))})")
    for old, newname in renames[:10]:
        print(dim(f"     {old} → {newname}"))
    if len(renames) > 10:
        print(dim(f"     … and {len(renames) - 10} more"))
    for p in changed[:10]:
        print(yellow(f"     overwrite {bucket}/{p} {dim(human_size(local[p]))}"))
    if len(changed) > 10:
        print(yellow(f"     … and {len(changed) - 10} more"))
    if args.dry_run:
        print(yellow("\n🧪 Dry run — nothing changed"))
        for p in new[:20]:
            print(f"  {bucket}/{p} {dim(human_size(local[p]))}")
        if len(new) > 20:
            print(dim(f"  … and {len(new) - 20} more"))
        for p in only_bucket[:20]:
            print(red(f"  would ask about deleting {bucket}/{p} ") + dim(human_size(remote[p][0])))
        if len(only_bucket) > 20:
            print(dim(f"  … and {len(only_bucket) - 20} more"))
        return 0
    delete = []
    if only_bucket:
        picked = filter_list(f"🗑️  Delete from s3://{BUCKET}/{bucket}/ (they match no local file) — untick to keep",
                             only_bucket, multi=True, initial=[True] * len(only_bucket),
                             extras=[[(human_size(remote[p][0]), "dim")] for p in only_bucket],
                             hint="type to filter · ↑/↓ move · Tab toggle · ^A toggle all shown · Enter done")
        delete = [f"{bucket}/{p}" for p, on in zip(only_bucket, picked) if on]
    uploads = [(f"{bucket}/{p}", os.path.join(folder, *p.split("/")), local[p]) for p in new + changed]
    if not (renames or uploads or delete):
        print(green("\nNothing to do ✨"))
        return 0
    print(f"\nThis will move {len(renames)}, upload {len(uploads)} ({len(changed)} overwriting), "
          f"delete {len(delete)} and keep {len(only_bucket) - len(delete)} in s3://{BUCKET}/{bucket}/")
    if not confirm("☁️  Go ahead?", default=False):
        print(yellow("👋 Cancelled."))
        return 0
    failed = move_keys([(f"{bucket}/{old}", f"{bucket}/{n}") for old, n in renames]) if renames else 0
    failed += run_uploads(uploads) if uploads else 0
    if delete and failed:
        print(yellow(f"\n⚠️  {failed} failure(s) above, so nothing was deleted; run it again once they are sorted"))
    elif delete:
        errors = delete_keys(delete)
        failed += len(errors)
        for e in errors:
            print(red(f"  ❌ {e.get('Key')}: {e.get('Message')}"))
    print(green("\n🎉 Done!") if not failed else red(f"\n⚠️  Done with {failed} failure(s)"))
    return 1 if failed else 0


def diff_command(args):
    """Show the ROMs that are in only one of a local folder (default: the current directory) and a bucket folder."""
    folder = os.path.abspath(os.path.expanduser(args.diff or os.getcwd()))
    if not os.path.isdir(folder):
        raise SystemExit(red(f"❌ {folder} is not a folder"))
    systems = sorted(load_manifest()["systems"], key=lambda s: s["name"].lower())
    guess = guess_system(systems, folder)
    i = filter_list("🔍 Which system is this folder compared with?", [f"{s['name']}  ({s['bucket']}/)" for s in systems],
                    cursor=guess or 0, hint="type to filter · ↑/↓ move · Enter continue · Esc cancel")
    if i is None:
        print(yellow("👋 Cancelled."))
        return 0
    bucket = systems[i]["bucket"]
    print(bold(f"🔍 Compare {systems[i]['name']}") + dim(f"  {folder} ↔ s3://{BUCKET}/{bucket}/"))
    local = local_sizes(folder)
    try:
        remote = list_with_etags(bucket + "/")
        only_local, only_bucket = plan_diff(
            local, remote, lambda p: local_fingerprint(os.path.join(folder, *p.split("/"))),
            lambda p, size, etag: bucket_fingerprint(f"{bucket}/{p}", size, etag))
    except (ClientError, BotoCoreError) as e:
        raise SystemExit(red(f"❌ {e}"))
    for title, paths, sizes, paint in (("Only in the folder", only_local, {p: local[p] for p in only_local}, green),
                                       ("Only in the bucket", only_bucket, {p: remote[p][0] for p in only_bucket}, yellow)):
        print(f"\n{bold(title)}: {len(paths)} ({human_size(sum(sizes.values()))})")
        for p in paths:
            print(paint(f"  {p} ") + dim(human_size(sizes[p])))
    if not only_local and not only_bucket:
        print(green("\nSame games on both sides ✨"))
    return 0


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
        out = s3_client(WRITE_PROFILE).delete_objects(
            Bucket=BUCKET, Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True})
        errors += out.get("Errors", [])
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
    except (ClientError, BotoCoreError) as e:
        raise SystemExit(red(f"❌ {e}"))
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
    except (ClientError, BotoCoreError) as e:
        raise SystemExit(red(f"❌ {e}"))
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
# muOS catalogue art, MUOS/info/catalogue/<system's muos_catalogue>/<folder>/<ROM name>.<ext>, and the media types that fill it
MUOS_MEDIA = (("box", ("covers", "3dboxes")), ("preview", ("screenshots", "titlescreens")))
SCRAPE_LAYOUTS = set(GAMELIST_FILES) | {"muos", "slot"}


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
    """Media downloads, gamelist entries and text files for one system's ROMs.

    rom_rels: ROM paths in the system folder; media_root: the system's media folder (esde's downloaded_media
    folder, muOS's catalogue folder or Slot's Labels folder); rom_dir: the system's ROM folder on the card;
    present(rom): is that ROM (going to be) on the card.
    Returns (jobs [(key, local path, size)], entries {ROM path: {gamelist tag: text}}, texts [(local path, text)]).
    """
    index = scrape_index(listing)
    jobs, entries, texts = [], {}, []
    for rom in sorted(rom_rels):
        if not present(rom):
            continue
        stem = os.path.splitext(rom)[0]
        found = index.get(stem, {})
        tags = gamelist_fields(meta.get(rom, {}))
        base = os.path.basename(stem)
        if layout_name == "muos":  # the catalogue is flat, even when the ROM is in a subfolder
            for folder, types in MUOS_MEDIA:
                mtype = next((t for t in types if t in found), None)
                if mtype:
                    key, size = found[mtype]
                    jobs.append((key, os.path.join(media_root, folder, base + os.path.splitext(key)[1]), size))
            if meta.get(rom, {}).get("desc"):
                texts.append((os.path.join(media_root, "text", base + ".txt"), meta[rom]["desc"] + "\n"))
            continue
        if layout_name == "slot":
            if SLOT_TYPE in found:
                key, size = found[SLOT_TYPE]
                jobs.append((key, os.path.join(media_root, base + ".png"), size))
            continue
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
    return jobs, entries, texts


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


def read_text(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def media_root_of(layout_name, system, base, es_dir):
    """The folder a system's scraped media goes in, for layouts that keep it apart from the ROMs."""
    if layout_name == "muos":
        return os.path.join(base, "MUOS", "info", "catalogue", system["muos_catalogue"])
    if layout_name == "slot":
        return os.path.join(base, "Labels", system["folders"]["slot"])
    return os.path.join(es_dir, "downloaded_media", system["bucket"])


def build_scrape_plan(layout_name, systems, data, extra, extra_texts, rom_rels, dest_of, es_dir, present, base):
    """Everything a sync installs from scrapes/: media jobs, gamelist entries per file, text files, ES-DE extras."""
    plan = {"jobs": [], "gamelists": defaultdict(dict), "extras": [], "writes": []}
    for s in systems:
        listing, meta = data[s["bucket"]]
        rom_dir = dest_of(s)
        media_root = media_root_of(layout_name, s, base, es_dir)
        jobs, entries, texts = plan_scrapes(layout_name, rom_rels.get(s["bucket"], ()), listing, meta, media_root,
                                            rom_dir,
                                            # Slot takes ROMs flat, whatever folder they are in in the bucket
                                            lambda rom, d=rom_dir: present(os.path.join(
                                                d, os.path.basename(rom) if layout_name == "slot" else rom)))
        plan["jobs"] += plan_downloads(jobs)
        for path, text in texts:  # only the ones that would change
            if not os.path.exists(path) or read_text(path) != text:
                plan["writes"].append((path, text))
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
          + (f", {len(plan['writes'])} text/collection/settings file(s)" if plan["writes"] else ""))


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


def media_name(layout_name, name):
    """How a firmware compares art names with ROM names: muOS ignores case, Slot also ignores bracketed tags."""
    if layout_name == "slot":
        name = re.sub(r"\s*[(\[][^)\]]*[)\]]", "", name)
    return name.strip().lower()


def stale_firmware_media(layout_name, systems, roms_dir, base):
    """Art files in muOS's catalogue (box, preview and text) or Slot's Labels folders whose ROM isn't on the card.

    Systems that share a catalogue folder are judged together. A folder whose ROM folders hold no ROMs is left alone.
    """
    groups = defaultdict(list)
    for s in systems:
        if s["folders"].get(layout_name):
            groups[media_root_of(layout_name, s, base, "")].append(os.path.join(roms_dir, s["folders"][layout_name]))
    stale = []
    for root, rom_dirs in sorted(groups.items()):
        stems = {media_name(layout_name, stem) for d in set(rom_dirs) if os.path.isdir(d) for stem in card_stems(d, True)}
        if not stems:
            continue
        for sub in ("box", "preview", "text") if layout_name == "muos" else (".",):
            folder = os.path.normpath(os.path.join(root, sub))
            for rel, full in walk_files(folder) if os.path.isdir(folder) else []:
                if media_name(layout_name, os.path.splitext(os.path.basename(rel))[0]) not in stems:
                    stale.append(full)
    return stale


def stale_media(layout_name, systems, roms_dir, es_dir, base=None):
    """Media files on the card whose ROM isn't in the system's ROM folder, for every system in the
    layout (not just the ones being synced). Systems with no ROM folder are left alone."""
    stale, seen = [], set()
    if layout_name in ("muos", "slot"):
        return stale_firmware_media(layout_name, systems, roms_dir, base)
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
        elif layout_name == "onion":
            base = os.path.join(rom_dir, "Imgs")
            stale += [full for rel, full in walk_files(base) if os.path.splitext(os.path.basename(rel))[0] not in stems] \
                if os.path.isdir(base) else []
    return stale


# --- Local mirror ---------------------------------------------------------------------------------

def load_settings():
    """Saved global settings: {"bucket": S3 bucket name, "endpoint": custom S3 endpoint URL, "profile"/"write_profile": aws profiles, "mirror": folder of the local mirror}."""
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
    """Set BUCKET and ENDPOINT from the saved settings, asking for the bucket (and an optional endpoint) on first run."""
    global BUCKET, ENDPOINT, PROFILE, WRITE_PROFILE
    settings = load_settings()
    PROFILE = os.environ.get("ROMS_PROFILE") or settings.get("profile") or "roms-readonly"
    WRITE_PROFILE = os.environ.get("ROMS_WRITE_PROFILE") or settings.get("write_profile") or "roms"
    BUCKET = os.environ.get("ROMS_BUCKET") or settings.get("bucket")
    ENDPOINT = os.environ.get("ROMS_ENDPOINT") or settings.get("endpoint") or None
    while not BUCKET:
        try:
            name = input("🪣 Which S3 bucket holds your ROMs? ").strip()
        except EOFError:
            raise SystemExit(red("❌ No bucket given"))
        name = re.sub(r"^s3://", "", name).strip("/")
        if name:
            save_setting("bucket", name)
            BUCKET = name
            try:
                url = input("🔗 Custom S3 endpoint URL (blank for AWS): ").strip()
            except EOFError:
                url = ""
            if url:
                save_setting("endpoint", url)
                ENDPOINT = url


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
    manifest = load_manifest(all_card_names())
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
    except (ClientError, BotoCoreError, OSError, SystemExit) as e:  # S3 failed, or the folder isn't a mirror
        print(yellow(f"  ⚠️  Couldn't refresh the mirror ({e}); using what it has"))
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
    ap.add_argument("--upload", nargs="?", const="")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--diff", nargs="?", const="")
    ap.add_argument("--m3u", nargs="?", const="")
    ap.add_argument("--chd", nargs="?", const="")
    ap.add_argument("--install-tools", action="store_true")
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
    local = [m for m, on in (("--m3u", args.m3u is not None), ("--chd", args.chd is not None), ("--install-tools", args.install_tools)) if on]
    if local:
        if len(local) > 1 or args.edit or args.upload is not None or args.diff is not None or args.upload_scrapes or args.clean_scrapes or args.mirror is not None or args.use_mirror or args.clear_mirror:
            raise SystemExit(red(f"❌ {local[0]} can't be combined with other modes"))
        if args.install_tools:
            return install_tools_command()
        return chd_command(args) if args.chd is not None else m3u_command(args)
    if args.replace and args.upload is None:
        raise SystemExit(red("❌ --replace only works together with --upload"))
    ensure_bucket()
    mirror_mode = args.mirror is not None or bool(args.use_mirror) or args.clear_mirror
    if args.edit + args.upload_scrapes + args.clean_scrapes + (args.upload is not None) + (args.diff is not None) + mirror_mode > 1:
        raise SystemExit(red("❌ Use only one of --edit, --upload, --diff, --upload-scrapes, --clean-scrapes, --mirror, "
                             "--use-mirror and --clear-mirror"))
    if args.upload is not None:
        return upload_command(args)
    if args.diff is not None:
        return diff_command(args)
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
    card = os.path.basename(base) or base
    manifest = load_manifest([card])
    systems = manifest["systems"]
    devices, layouts = manifest["devices"], manifest["layouts"]
    saved = load_cards().get(card)
    dirs = None
    setup = saved_setup(saved, devices, layouts)
    if setup:
        device, layout_name = setup
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
    unzip = layout.get("unzip", False)  # ROMs go in flat and unzipped (Slot)
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
            if plan_downloads([(k, os.path.join(roms_dir, s["folders"][layout_name], rom_rel(k, unzip)), size)], unzip):
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
                rom_jobs.append((key, os.path.join(dest, rom_rel(key, unzip)), have[key]))
            else:
                missing.append(key)
    report_missing(missing, "ROM(s)")
    # systems can share a folder (Onion: WS, NGP), so a folder's expected files are the union over all of them
    for dest in sorted({dest_of(s) for s in chosen if available(s)}):
        extras += find_extras(dest, [k for t in systems if dest_of(t) == dest for k in available(t)], unzip)

    bios_keys = sorted({"BIOS/" + f for s in chosen for f in s["bios"]["files"]})
    bios_have = list_sizes("BIOS/") if bios_keys else {}
    bios_jobs = [(k, os.path.join(bios_dir, k[len("BIOS/"):]), bios_have[k])
                 for k in bios_keys if k in bios_have]
    report_missing([k for k in bios_keys if k not in bios_have], "BIOS file(s)")

    rom_todo, bios_todo = plan_downloads(rom_jobs, unzip), plan_downloads(bios_jobs)
    print(f"\n💿 ROMs: {bold(str(len(rom_todo)))} to download "
          f"({human_size(sum(j[2] or 0 for j in rom_todo))}), "
          f"{len(rom_jobs) - len(rom_todo)} already present")
    print(f"🧠 BIOS: {bold(str(len(bios_todo)))} to download "
          f"({human_size(sum(j[2] or 0 for j in bios_todo))}), "
          f"{len(bios_jobs) - len(bios_todo)} already present")
    if extras:
        print(f"🗑️  Local ROMs no longer in the selection: {bold(str(len(extras)))}")
    es_dir = os.path.join(base, "ES-DE")
    scrapes = layout_name in SCRAPE_LAYOUTS
    scraped = {}

    def scrape_plan(present):
        if not scraped:
            print("🖼️  Reading scraped data...")
            scraped["data"] = load_scrape_data(chosen, layout_name == "esde")
            scraped["rels"] = {s["bucket"]: [k.split("/", 1)[1] for k in available(s) if k in listings[s["bucket"]]]
                               for s in chosen}
        if unzip:  # a ROM that's extracted from its archive is on the card under another extension
            present = lambda path, exists=present: exists(path) or archive_extracted(path)  # noqa: E731
        return build_scrape_plan(layout_name, chosen, *scraped["data"], scraped["rels"], dest_of, es_dir, present, base)

    if args.dry_run:
        print(yellow("\n🧪 Dry run — nothing downloaded or deleted"))
        for key, path, _ in rom_todo + bios_todo:
            print(f"  {key} {dim('→')} {path}")
        for path in extras:
            print(f"  {red('would delete')} {path}")
        if scrapes:
            describe_scrape_plan(scrape_plan(lambda path: True))
            print(f"🧹 Media on the card for ROMs it doesn't have: {len(stale_media(layout_name, manifest['systems'], roms_dir, es_dir, base))} file(s) to remove")
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
    if unzip:
        for path, error in unzip_roms([j[1] for j in rom_todo]):
            failed += 1
            print(red(f"  ❌ {os.path.relpath(path, roms_dir)}: {error}"))
    stale = []
    if scrapes:
        plan = scrape_plan(os.path.exists)
        describe_scrape_plan(plan)
        failed += apply_scrape_plan(plan, base)
        stale = stale_media(layout_name, manifest["systems"], roms_dir, es_dir, base)
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

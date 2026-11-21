"""ROCKNIX's custom collections: staged on the card, installed on the device by a script run from Ports.

ROCKNIX's EmulationStation reads custom collections and its settings only from internal storage
(/storage/.config/emulationstation), which a computer can't reach. Sync writes the collection files to STAGING in the
card's ROM folder (on the device always /storage/roms, the card's roms/ bind-mounted there) and puts SCRIPT in Ports;
run there, it copies them to EmulationStation's folder, lists them in CollectionSystemsCustom, turns on the Art Book Next
art sync put in ART_DIR, and restarts EmulationStation (which keeps its settings in memory and doesn't save them when
stopped), so they show. It only removes or unlists collections it installed itself (recorded on the device)."""
import os

from . import store

STAGING = os.path.join("roms", ".sync-roms-collections")
SCRIPT = os.path.join("roms", "ports", "Install Collections.sh")
# Art Book Next's customizations on ROCKNIX: ~/roms/_userdata/theme-customizations/art-book-next/ (HOME is /storage)
ART_DIR = os.path.join("roms", "_userdata", "theme-customizations", "art-book-next")

SCRIPT_TEXT = r'''#!/bin/bash
# Written by sync-roms. EmulationStation reads custom collections only from internal storage: run this from Ports
# after a sync that changed the card's collections. It copies them from the card, lists them, turns on their Art Book
# Next art, and restarts EmulationStation so they show. It removes itself once there is nothing left to install.
SELF="$0"
case "$SELF" in /*) ;; *) SELF="$PWD/$SELF" ;; esac
ROMS="$(cd "${SELF%/*}/.." && pwd)" || exit 1
ES="${SYNC_ROMS_ES_DIR:-/storage/.config/emulationstation}"
python3 - "$ROMS" "$ES" "$SELF" <<'PY' || exit 1
import os, re, shutil, sys

roms, es, script = sys.argv[1:4]
stage = os.path.join(roms, ".sync-roms-collections")
art = os.path.join(roms, "_userdata", "theme-customizations", "art-book-next")
dest = os.path.join(es, "collections")
settings_path = os.path.join(es, "es_settings.cfg")
manifest = os.path.join(es, "sync-roms-collections.txt")


def staged():
    try:
        files = sorted(os.listdir(stage))
    except FileNotFoundError:
        return []
    return [f[7:-4] for f in files if f.startswith("custom-") and f.endswith(".cfg") and len(f) > 11]


def escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def unescape(s):
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&")):
        s = s.replace(a, b)
    return s


def entry(name):
    return re.compile(r'<string name="%s" value="([^"]*)"\s*/>' % re.escape(escape(name)))


def get(name):
    match = entry(name).search(text)
    return unescape(match.group(1)) if match else None


def put(name, value):
    global text
    line = '<string name="%s" value="%s" />' % (escape(name), escape(value))
    match = entry(name).search(text)
    if match:
        text = text[:match.start()] + line + text[match.end():]
    else:
        end = text.rfind("</config>")
        text = text[:end] + "\t" + line + "\n" + text[end:]


try:
    with open(manifest, encoding="utf-8") as f:
        installed = [n for n in f.read().split("\n") if n]
except FileNotFoundError:
    installed = []
os.makedirs(dest, exist_ok=True)
new = []
for name in staged():
    target = os.path.join(dest, "custom-%s.cfg" % name)
    if name not in installed and os.path.exists(target):
        print("Skipped %s: EmulationStation already has a collection of that name" % name)
        continue
    shutil.copyfile(os.path.join(stage, "custom-%s.cfg" % name), target)
    new.append(name)
gone = [n for n in installed if n not in new]
for name in gone:
    try:
        os.remove(os.path.join(dest, "custom-%s.cfg" % name))
    except FileNotFoundError:
        pass

try:
    with open(settings_path, encoding="utf-8") as f:
        text = f.read()
except FileNotFoundError:
    text = ""
if "</config>" not in text:
    text = '<?xml version="1.0"?>\n<config>\n</config>\n'
before = text
enabled = [n for n in (get("CollectionSystemsCustom") or "").split(",") if n and n not in gone]
put("CollectionSystemsCustom", ",".join(enabled + [n for n in new if n not in enabled]))
theme = get("ThemeSet") or ""
if theme in ("", "system-theme") or "art-book-next" in theme:  # system-theme is ROCKNIX's link to Art Book Next
    with_art = False
    for name in new:
        if os.path.isfile(os.path.join(art, "artwork", name + ".png")):
            put("subset.%s.system-view-artwork" % name, "custom")
            with_art = True
        if os.path.isfile(os.path.join(art, "logos", name + ".svg")):
            put("subset.%s.system-logos" % name, "custom")
    for name, value in (("subset.distribution", "rocknix"), ("UseCustomCollectionsSystemEx", "false")):
        if with_art and not get(name):
            put(name, value)
if text != before:
    with open(settings_path + ".tmp", "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(settings_path + ".tmp", settings_path)
with open(manifest, "w", encoding="utf-8") as f:
    f.write("".join(n + "\n" for n in new))
print("Installed %d collection(s), removed %d" % (len(new), len(gone)))
if not staged():
    os.remove(script)
PY
if command -v systemd-run >/dev/null 2>&1 &&
    systemd-run --on-active=3 systemctl try-restart essway.service emustation.service >/dev/null 2>&1; then
  echo "EmulationStation restarts in a moment."
else
  echo "Restart EmulationStation to see the collections."
fi
'''


def write_script(base, keep):
    """Put the install script on the card at base when keep (collections to install or uninstall), else remove it.
    Returns whether the card changed."""
    path = os.path.join(base, SCRIPT)
    if not keep:
        try:
            os.remove(path)
            return True
        except FileNotFoundError:
            return False
    data = SCRIPT_TEXT.encode("utf-8")
    try:
        if os.path.getsize(path) == len(data):
            with open(path, "rb") as f:
                if f.read() == data:
                    return False
    except FileNotFoundError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    store.replace_file(path, data)
    try:
        os.chmod(path, 0o755)
    except OSError:  # a FAT card has no modes; ROCKNIX runs a port with bash anyway
        pass
    return True

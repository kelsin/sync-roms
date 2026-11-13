"""The .psvita files ES-DE launches installed Vita3K games with: one per Vita zip, holding the game's title id."""
import os
import re
import struct
import zipfile

from . import chd, downloads

BUCKET = "psvita"
TITLE_ID = re.compile(r"\[([A-Z]{4}\d{5})\]")
VERSION = re.compile(r"\[v(\d+(?:\.\d+)*)\]")


def kind(name):
    """"dlc", "update" or "game", from the tags in a Vita file name."""
    name = os.path.basename(name)
    if "[DLC-" in name:
        return "dlc"
    return "update" if "[PATCH]" in name else "game"


def is_extra(key):
    """Whether a storage key is a Vita DLC or update."""
    return key.startswith(BUCKET + "/") and kind(key) != "game"


def extras(game_keys, folder_keys):
    """{game key: [extra keys]}: each psvita game's DLC (sorted) then its newest update, matched by title id."""
    by_id = {}
    for key in folder_keys:
        found = TITLE_ID.search(os.path.basename(key))
        if found and is_extra(key):
            by_id.setdefault(found.group(1), []).append(key)

    def version(key):
        v = VERSION.search(key)
        return (1, tuple(int(n) for n in v.group(1).split("."))) if v else (0, ())

    result = {}
    for game in game_keys:
        found = TITLE_ID.search(os.path.basename(game))
        if not found or not game.startswith(BUCKET + "/") or kind(game) != "game":
            continue
        mine = by_id.get(found.group(1), [])
        updates = [k for k in mine if kind(k) == "update"]
        chosen = sorted(k for k in mine if kind(k) == "dlc") + ([max(updates, key=version)] if updates else [])
        if chosen:
            result[game] = chosen
    return result


def sfo_values(data):
    """{key: str} of the string entries in a param.sfo."""
    key_table, data_table, count = struct.unpack_from("<III", data, 8)
    values = {}
    for i in range(count):
        key_off, fmt, length, _, data_off = struct.unpack_from("<HHIII", data, 20 + 16 * i)
        key = data[key_table + key_off:data.index(b"\0", key_table + key_off)].decode()
        if fmt in (0x204, 0x004):  # utf-8 string (0x004 is the unterminated form)
            values[key] = data[data_table + data_off:data_table + data_off + length].split(b"\0")[0].decode("utf-8", "replace")
    return values


def title_id(path):
    """(title id, error) of the one game in a Vita zip: the TITLE_ID of its category-gd (app) param.sfo."""
    with zipfile.ZipFile(path) as z:
        apps = set()
        for name in z.namelist():
            if name == "sce_sys/param.sfo" or name.endswith("/sce_sys/param.sfo"):
                values = sfo_values(z.read(name))
                if values.get("CATEGORY") == "gd" and values.get("TITLE_ID"):
                    apps.add(values["TITLE_ID"])
    if len(apps) != 1:
        return None, "no game in the zip" if not apps else "more than one game in the zip"
    return apps.pop(), None


def make_psvita(path):
    """Write the .psvita file beside a Vita zip, which is left alone (Vita3K installs it as it is).
    None on success, else the error."""
    out = os.path.splitext(path)[0] + ".psvita"
    try:
        game, error = title_id(path)
        if error:
            return error
        part = chd.part_path(out)
        with open(part, "w") as f:
            f.write(game)
        os.replace(part, out)
    except (OSError, zipfile.BadZipFile, struct.error, ValueError) as e:
        return str(e)


def add_psvita_files(dests):
    """Write the missing .psvita file beside each zip in the given folders. Returns [(zip, error)] for the failures."""
    failures = []
    for dest in dests:
        for root, files in downloads.walk_roms(dest):
            for f in files:
                path = os.path.join(root, f)
                if f.lower().endswith(".zip") and kind(f) == "game" and not os.path.lexists(os.path.splitext(path)[0] + ".psvita"):
                    error = make_psvita(path)
                    if error:
                        failures.append((path, error))
    return failures

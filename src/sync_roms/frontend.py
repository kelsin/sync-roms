"""ES-DE/Knulli/EmuDeck/NextUI/ROCKNIX custom collection files."""
import contextlib
import os
import re
from xml.sax import saxutils

from . import cardfs, downloads, rocknix_collections, store, ui

FRONTEND_LAYOUTS = {"esde", "knulli", "emudeck", "nextui", "rocknix"}
_LABELS = {"esde": "ES-DE", "knulli": "Knulli", "emudeck": "EmuDeck", "nextui": "NextUI",
           "rocknix": "ROCKNIX"}
ESDE_LAYOUTS = ("esde", "emudeck")  # layouts whose frontend is ES-DE
_DROPPED = '*",./:;<>\\|\n\t\r'  # characters ES-DE rejects in a collection name
_UNESCAPE = {"&quot;": '"', "&apos;": "'"}
_ESCAPE = {'"': "&quot;", "'": "&apos;"}


def safe_name(name):
    """name without the characters ES-DE rejects in a collection name, trimmed."""
    return "".join(c for c in name if c not in _DROPPED).strip()


def esde_dir(layout_name, base):
    """ES-DE's data folder: on the card for esde; on this computer for emudeck (EmuDeck's ES-DE keeps it there)."""
    if layout_name == "emudeck":
        return os.environ.get("ESDE_APPDATA_DIR") or os.path.expanduser("~/ES-DE")
    return os.path.join(base, "ES-DE")


def _root(layout_name, base):
    if layout_name in ESDE_LAYOUTS:
        return esde_dir(layout_name, base)
    return os.path.join(base, "system", "configs", "emulationstation")


def collection_path(layout_name, base, name):
    if layout_name == "nextui":  # one ROM path per line; no settings file lists it
        return os.path.join(base, "Collections", f"{name}.txt")
    if layout_name == "rocknix":  # staged on the card; its install script copies them to internal storage
        return os.path.join(base, rocknix_collections.STAGING, f"custom-{name}.cfg")
    return os.path.join(_root(layout_name, base), "collections", f"custom-{name}.cfg")


def settings_path(layout_name, base):
    if layout_name in ESDE_LAYOUTS:
        return os.path.join(_root(layout_name, base), "settings", "es_settings.xml")
    return os.path.join(_root(layout_name, base), "es_settings.cfg")


def collection_line(layout_name, folder, rel):
    if layout_name == "nextui":
        return f"/Roms/{folder}/{rel}"
    if layout_name == "rocknix":  # the card's roms/ is mounted there
        return f"/storage/roms/{folder}/{rel}"
    return f"%ROMPATH%/{folder}/{rel}" if layout_name in ESDE_LAYOUTS else f"./roms/{folder}/{rel}"


def _string_setting(name):
    """Matches name's entry, each XML special character escaped or not (ES and older sync-roms leave some as they are)."""
    entities = {"&": "&amp;", "<": "&lt;", ">": "&gt;", **_ESCAPE}
    name = "".join(f"(?:{entities[c]}|{re.escape(c)})" if c in entities else re.escape(c) for c in name)
    return re.compile(rf'<string name="{name}" value="([^"]*)"\s*/>')


def get_string(text, name):
    """The value of the frontend settings file's <string name=...> entry, or None when it has none."""
    match = _string_setting(name).search(text)
    return saxutils.unescape(match.group(1), _UNESCAPE) if match else None


def set_enabled(text, layout_name, add, remove):
    """text (the frontend's settings file) with the add names enabled and the remove names not, as custom collections."""
    match = _string_setting("CollectionSystemsCustom").search(text)
    names = [n for n in saxutils.unescape(match.group(1), _UNESCAPE).split(",") if n] if match else []
    names = [n for n in names if n not in remove]
    names += sorted(n for n in set(add) if n not in names)
    return set_string(text, layout_name, "CollectionSystemsCustom", ",".join(names))


def set_string(text, layout_name, name, value):
    """text (the frontend's settings file) with its <string name=...> entry set to value, the rest left as it is."""
    match = _string_setting(name).search(text)
    line = f'<string name="{saxutils.escape(name, _ESCAPE)}" value="{saxutils.escape(value, _ESCAPE)}" />'
    if match:
        return text[:match.start()] + line + text[match.end():]
    if layout_name in ESDE_LAYOUTS:
        if text and not text.endswith("\n"):
            text += "\n"
        return (text or '<?xml version="1.0"?>\n') + line + "\n"
    if not text:
        return f'<?xml version="1.0"?>\n<config>\n\t{line}\n</config>\n'
    end = text.rfind("</config>")
    if end < 0:
        return text + ("" if text.endswith("\n") else "\n") + "\t" + line + "\n"
    return text[:end] + "\t" + line + "\n" + text[end:]


def remove_string(text, name):
    """text (the frontend's settings file) without its <string name=...> entry and that entry's line."""
    return re.sub(rf'[ \t]*{_string_setting(name).pattern}\n?', "", text)


def plan_collections(layout_name, base, wanted, owned, keep=False):
    """What to write and delete on the card for the wanted {name: lines}, given the names sync-roms owns. keep
    (--no-delete): the retired ones stay as they are (see retired)."""
    plan = {"writes": [], "deletes": [], "enable": set(), "disable": set(), "owned": [], "warnings": []}
    for name in sorted(wanted):
        path = collection_path(layout_name, base, name)
        if name not in owned and os.path.exists(path):
            plan["warnings"].append(f"{_LABELS[layout_name]} already has a custom collection {name} "
                                    f"that sync-roms didn't write; skipped")
            continue
        text = "\n".join(wanted[name]) + "\n"
        if not same(path, text):
            plan["writes"].append((path, text))
        plan["enable"].add(name)
    plan["owned"] = sorted(plan["enable"])
    for name in retired(plan, owned, keep):
        path = collection_path(layout_name, base, name)
        if os.path.exists(path):
            plan["deletes"].append(path)
    return plan


def retired(plan, owned, keep=False):
    """The names sync-roms owns that plan doesn't enable, added to its "disable"; a recorded name that isn't a valid
    collection name is left out with a warning in plan. With keep (--no-delete) none is returned or disabled: they are
    listed in plan["kept"] and stay in its "owned", so a later sync without --no-delete removes them."""
    names = []
    for name in dict.fromkeys(owned):
        if not name or safe_name(name) != name:
            plan["warnings"].append(f"ignoring the recorded collection name {name!r}; it isn't a valid name")
        elif name not in plan["enable"]:
            if keep:
                plan.setdefault("kept", []).append(name)
                plan["owned"] = sorted({*plan["owned"], name})
                continue
            plan["disable"].add(name)
            names.append(name)
    return names


def same(path, text):
    """Whether the file at path holds text; only a file of the same size is read."""
    try:
        return os.path.getsize(path) == len(text.encode("utf-8")) and _read(path) == text
    except OSError:
        return False


def _read(path):
    """path's text, or None when it can't be read."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def emudeck_problem(base, roms):
    """None when this computer's ES-DE serves the emudeck card at base (roms: its ROM folder), else why it doesn't."""
    es_dir = esde_dir("emudeck", base)
    if not os.path.isdir(es_dir):
        return f"ES-DE isn't set up on this computer (no {es_dir})"
    try:
        used = get_string(cardfs.text(settings_path("emudeck", base)), "ROMDirectory")
    except (OSError, UnicodeDecodeError):
        used = ""
    if not used or os.path.realpath(used) != os.path.realpath(roms):
        return f"ES-DE on this computer ({es_dir}) doesn't use this card's ROMs (its ROMDirectory isn't {roms})"
    return None


def write_files(plan):
    """Write plan's files (LF line ends)."""
    for path, text in plan["writes"]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        store.replace_file(path, text, newline="\n")


def apply_collections(plan, layout_name, base):
    """Write and delete plan's collection files and list or unlist them in the settings file; True when that file changed
    (for rocknix, which has no settings on the card: when its install script was written or removed)."""
    write_files(plan)
    for path in plan["deletes"]:
        with contextlib.suppress(FileNotFoundError):
            os.remove(path)
    if layout_name == "rocknix":
        return rocknix_collections.write_script(base, bool(plan["owned"] or plan["deletes"]))
    if layout_name == "nextui" or not (plan["enable"] or plan["disable"]):
        return False
    path = settings_path(layout_name, base)
    return cardfs.write_text(path, set_enabled(cardfs.text(path), layout_name, plan["enable"], plan["disable"]))


def collection_roms(layout_name, collections, systems, on_card, folders=None):
    """(safe collection name, system folder, ROM path in it) of each of the collections' games that is on the card, on
    the systems it syncs, in the collections' order. A collection whose name has no character left is left out.

    folders: {key: its game's folder} (m3u.game_folders), for layouts that keep each disc game in a folder of its own."""
    by_bucket = {s["bucket"]: s for s in systems}
    for collection in collections:
        name = safe_name(collection["name"])
        for game in collection["games"]:
            system = by_bucket.get(game["system"])
            folder = system and system["folders"].get(layout_name)
            if not folder:
                continue
            rel = downloads.rom_rel(game["bucket"], folders=folders)
            if on_card(system, rel) and name:
                yield name, folder, rel


def wanted_collections(layout_name, collections, systems, on_card, folders=None):
    """{safe name: lines} of the collections' games that are on the card (collection_roms); collections of one name
    share its lines, each line once."""
    wanted = {}
    for name, folder, rel in collection_roms(layout_name, collections, systems, on_card, folders):
        lines = wanted.setdefault(name, [])
        line = collection_line(layout_name, folder, rel)
        if line not in lines:
            lines.append(line)
    return wanted


def describe_collections(plan, layout_name):
    """Print what apply_collections(plan) would do."""
    for path, text in plan["writes"]:
        print(ui.dim(f"💖 would write {os.path.basename(path)} ({text.count(chr(10))} game(s))"))
    for path in plan["deletes"]:
        print(ui.dim(f"💖 would delete {os.path.basename(path)}"))
    if layout_name == "rocknix":
        if plan["writes"] or plan["deletes"]:
            print(ui.dim(f"💖 then run {os.path.basename(rocknix_collections.SCRIPT)[:-3]} from Ports on the device"))
    elif layout_name != "nextui":
        settings = os.path.basename(settings_path(layout_name, ""))
        if plan["enable"]:
            print(ui.dim(f"💖 would enable in {settings}: {', '.join(sorted(plan['enable']))}"))
        if plan["disable"]:
            print(ui.dim(f"💖 would unlist in {settings}: {', '.join(sorted(plan['disable']))}"))
    for warning in plan["warnings"]:
        ui.warn(warning)

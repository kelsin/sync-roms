"""ES-DE/Knulli custom collection files."""
import os
import re
from xml.sax import saxutils

from . import downloads, ui

FRONTEND_LAYOUTS = {"esde", "knulli"}
_LABELS = {"esde": "ES-DE", "knulli": "Knulli"}
_DROPPED = '*",./:;<>\\|\n\t\r'  # characters ES-DE rejects in a collection name
_UNESCAPE = {"&quot;": '"', "&apos;": "'"}
_ESCAPE = {'"': "&quot;", "'": "&apos;"}
_SETTING = re.compile(r'<string name="CollectionSystemsCustom" value="([^"]*)"\s*/>')


def safe_name(name):
    """name without the characters ES-DE rejects in a collection name, trimmed."""
    return "".join(c for c in name if c not in _DROPPED).strip()


def _root(layout_name):
    return "ES-DE" if layout_name == "esde" else os.path.join("system", "configs", "emulationstation")


def collection_path(layout_name, base, name):
    return os.path.join(base, _root(layout_name), "collections", f"custom-{name}.cfg")


def settings_path(layout_name, base):
    if layout_name == "esde":
        return os.path.join(base, "ES-DE", "settings", "es_settings.xml")
    return os.path.join(base, _root(layout_name), "es_settings.cfg")


def collection_line(layout_name, folder, rel):
    return f"%ROMPATH%/{folder}/{rel}" if layout_name == "esde" else f"./roms/{folder}/{rel}"


def set_enabled(text, layout_name, add, remove):
    """text (the frontend's settings file) with the add names enabled and the remove names not, as custom collections."""
    match = _SETTING.search(text)
    names = [n for n in saxutils.unescape(match.group(1), _UNESCAPE).split(",") if n] if match else []
    names = [n for n in names if n not in remove]
    names += sorted(n for n in set(add) if n not in names)
    value = saxutils.escape(",".join(names), _ESCAPE)
    line = f'<string name="CollectionSystemsCustom" value="{value}" />'
    if match:
        return text[:match.start()] + line + text[match.end():]
    if layout_name == "esde":
        if text and not text.endswith("\n"):
            text += "\n"
        return (text or '<?xml version="1.0"?>\n') + line + "\n"
    if not text:
        return f'<?xml version="1.0"?>\n<config>\n\t{line}\n</config>\n'
    end = text.rfind("</config>")
    if end < 0:
        return text + ("" if text.endswith("\n") else "\n") + "\t" + line + "\n"
    return text[:end] + "\t" + line + "\n" + text[end:]


def plan_collections(layout_name, base, wanted, owned):
    """What to write and delete on the card for the wanted {name: lines}, given the names sync-roms owns."""
    plan = {"writes": [], "deletes": [], "enable": set(), "disable": set(), "owned": [], "warnings": []}
    for name in sorted(wanted):
        path = collection_path(layout_name, base, name)
        if name not in owned and os.path.exists(path):
            plan["warnings"].append(f"{_LABELS[layout_name]} already has a custom collection {name} "
                                    f"that sync-roms didn't write; skipped")
            continue
        plan["writes"].append((path, "\n".join(wanted[name]) + "\n"))
        plan["enable"].add(name)
    plan["owned"] = sorted(plan["enable"])
    for name in dict.fromkeys(owned):
        if safe_name(name) != name:
            plan["warnings"].append(f"ignoring the recorded collection name {name!r}; it isn't a valid name")
            continue
        if name in plan["enable"]:
            continue
        plan["disable"].add(name)
        path = collection_path(layout_name, base, name)
        if os.path.exists(path):
            plan["deletes"].append(path)
    return plan


def apply_collections(plan, layout_name, base):
    for path, text in plan["writes"]:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    for path in plan["deletes"]:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    if not (plan["enable"] or plan["disable"]):
        return
    path = settings_path(layout_name, base)
    old = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = f.read()
    new = set_enabled(old, layout_name, plan["enable"], plan["disable"])
    if new != old:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new)


def wanted_collections(layout_name, collections, systems, on_card):
    """{safe name: lines} of the collections' games that are on the card, on the systems it syncs."""
    by_bucket = {s["bucket"]: s for s in systems}
    wanted = {}
    for collection in collections:
        name = safe_name(collection["name"])
        lines = []
        for game in collection["games"]:
            system = by_bucket.get(game["system"])
            if not system:
                continue
            rel = downloads.rom_rel(game["bucket"], False)
            if on_card(system, rel):
                lines.append(collection_line(layout_name, system["folders"][layout_name], rel))
        if name and lines:
            merged = wanted.setdefault(name, [])
            merged.extend(line for line in lines if line not in merged)
    return wanted


def describe_collections(plan, layout_name):
    """Print what apply_collections(plan) would do."""
    for path, text in plan["writes"]:
        print(ui.dim(f"💖 would write {os.path.basename(path)} ({text.count(chr(10))} game(s))"))
    for path in plan["deletes"]:
        print(ui.dim(f"💖 would delete {os.path.basename(path)}"))
    settings = os.path.basename(settings_path(layout_name, ""))
    if plan["enable"]:
        print(ui.dim(f"💖 would enable in {settings}: {', '.join(sorted(plan['enable']))}"))
    if plan["disable"]:
        print(ui.dim(f"💖 would unlist in {settings}: {', '.join(sorted(plan['disable']))}"))
    for warning in plan["warnings"]:
        ui.warn(warning)

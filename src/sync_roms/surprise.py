"""Surprise: a few random full English games per system, rotated on a schedule. This part holds the candidate rules."""
import posixpath
import re

from . import m3u

SLOTS = 10
RECOMMENDED_SHARE = 2 / 3
DEFAULT_TTL_DAYS = 183
COLLECTION = "Surprise"

ENGLISH_REGIONS = {"USA", "World", "Europe", "UK", "United Kingdom", "Australia", "Canada"}
REGIONS = ENGLISH_REGIONS | {
    "Japan", "Korea", "Asia", "China", "Taiwan", "Hong Kong", "India", "Israel", "Turkey", "UAE", "Brazil", "Argentina",
    "Chile", "Mexico", "Latin America", "France", "Germany", "Spain", "Italy", "Netherlands", "Sweden", "Denmark",
    "Finland", "Norway", "Scandinavia", "Poland", "Portugal", "Russia", "Greece", "Ireland", "Switzerland", "Austria",
    "Belgium", "Croatia", "Czech", "Hungary", "New Zealand", "South Africa", "Unknown"}
NOT_FULL = ("Proto", "Beta", "Demo", "Sample", "Kiosk", "Pirate", "Hack", "Unl")
RERELEASE = ("Virtual Console", "Switch Online", "Classic Mini", "Mini Mix", "Mega Drive Mini", "Genesis Mini",
             "Collection", "Anthology", "Archives", "Sega Ages", "Sega Channel", "Evercade", "Steam", "GOG",
             "Retro-Bit", "Limited Run", "e-Reader", "QUByte Classics")
LANGUAGE = re.compile(r"^[A-Z][a-z](-[A-Za-z]+)?$")


def _paren_groups(name):
    return [[p.strip() for p in g.split(",")] for g in re.findall(r"\(([^)]*)\)", name)]


def _english(name):
    groups = _paren_groups(name)
    for parts in groups:
        if all(LANGUAGE.match(p) for p in parts):
            return any(p == "En" or p.startswith("En-") for p in parts)
    for parts in groups:
        if all(p in REGIONS for p in parts):
            return bool(ENGLISH_REGIONS & set(parts))
    return True


def is_candidate(key, system, family, bios):
    """Whether the bucket key is a full English game: no BIOS, prototype, beta, demo, hack, re-release or compilation."""
    base = posixpath.basename(key)
    stem = posixpath.splitext(base)[0]
    if base in bios or "[BIOS]" in base:
        return False
    if family is not None:
        title = family["parents"].get(stem)
        return title is not None and not any(parts[0].split()[:1] == ["Japan"] for parts in _paren_groups(title))
    if re.search(r"\[[bh][^\]]*\]", stem, re.I):
        return False
    groups = _paren_groups(stem)
    if any(p.startswith(NOT_FULL) for parts in groups for p in parts):
        return False
    if any(t in g for g in re.findall(r"\(([^)]*)\)", stem) for t in RERELEASE):
        return False
    return _english(stem)


def units(system, keys, family, bios):
    """The candidate games among keys, each a list of its keys (a multi-disc game's playlist first, then its discs)."""
    keys = sorted(k for k in keys if not k.endswith("/"))
    groups = m3u.file_groups(keys)
    out, seen = [], set()
    for k in keys:
        unit = groups.get(k, [k])
        if tuple(unit) not in seen:
            seen.add(tuple(unit))
            if is_candidate(unit[0], system, family, bios):
                out.append(unit)
    return out

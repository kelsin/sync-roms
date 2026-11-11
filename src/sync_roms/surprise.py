"""Surprise: a few random full English games per system, rotated on a schedule. This part holds the candidate rules."""
import posixpath
import re

from . import m3u, store

SLOTS = 10
RECOMMENDED_SHARE = 2 / 3
DEFAULT_TTL_DAYS = 183
COLLECTION = "Surprise"

ENGLISH_REGIONS = {"USA", "World", "Europe", "UK", "United Kingdom", "Australia", "Canada"}
REGIONS = ENGLISH_REGIONS | {
    "Japan", "Korea", "Asia", "China", "Taiwan", "Hong Kong", "India", "Israel", "Turkey", "UAE", "Brazil", "Argentina",
    "Chile", "Mexico", "Latin America", "France", "Germany", "Spain", "Italy", "Netherlands", "Sweden", "Denmark",
    "Finland", "Norway", "Scandinavia", "Poland", "Portugal", "Russia", "Greece", "Ireland", "Switzerland", "Austria",
    "Belgium", "Croatia", "Czech", "Hungary", "New Zealand", "South Africa", "Ukraine", "Bulgaria", "Romania",
    "Serbia", "Slovakia", "Slovenia", "Estonia", "Latvia", "Lithuania", "Iceland", "Indonesia", "Thailand", "Vietnam",
    "Philippines", "Malaysia", "Singapore", "Egypt", "Saudi Arabia", "Peru", "Colombia", "Venezuela", "Uruguay",
    "Macao", "Unknown"}
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


def _surprise(system, unit):
    out = {"system": system, "bucket": unit[0], "title": store.key_title(unit[0])}
    if unit[1:]:
        out["files"] = unit[1:]
    return out


def pick(pools, kept, need, recommended, recent, others_current, rng):
    """Up to need new surprises from pools ({system bucket: [units]}): about two thirds (kept ones counted) from the
    recommended systems, spread evenly, slots passing on when a system runs out. Unused games come first, then ones
    surprised before (recent), then ones another card currently holds."""
    left = {b: list(u) for b, u in pools.items()}
    groups = {g: [b for b in sorted(left) if (b in recommended) == g] for g in (True, False)}
    for g in groups.values():
        rng.shuffle(g)
    kept_rec = sum(1 for k in kept if k["system"] in recommended)
    want_rec = min(max(round(SLOTS * RECOMMENDED_SHARE) - kept_rec, 0), need)
    out = []

    def tier(unit):
        return 2 if unit[0] in others_current else 1 if unit[0] in recent else 0

    given = dict.fromkeys(left, 0)
    for k in kept:
        if k["system"] in given:
            given[k["system"]] += 1

    def fill(group, slots):
        """Give each slot to the group's system with the fewest picks that still has games, so systems that run out
        pass their slots on and the rest stay even. Returns the unused slots."""
        while slots:
            open_ = [b for b in groups[group] if left[b]]
            if not open_:
                break
            b = min(open_, key=given.__getitem__)
            best = min(map(tier, left[b]))
            unit = rng.choice([u for u in left[b] if tier(u) == best])
            left[b].remove(unit)
            given[b] += 1
            out.append(_surprise(b, unit))
            slots -= 1
        return slots

    rest = fill(False, need - want_rec + fill(True, want_rec))
    fill(True, rest)
    return out

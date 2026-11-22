"""How much of a card's space its games take: ROM files plus the scraped files its layout installs, from the size cache."""
import re
from collections import namedtuple

from . import collections as colls, inventory, scrape_plan, store, vita

Usage = namedtuple("Usage", "bytes count partial")


# each system's scrapes listing indexed by ROM, and each ROM's scrape bytes per (layout, system), for one cache version
_scrapes = {"version": None, "by_stem": {}, "costs": {}}


def _scrapes_by_stem(bucket):
    """The scrape_plan.scrape_index ({ROM stem: {media type: (key, size)}}) of the system's scrapes listing, or None
    when it isn't cached. Kept for the run until the cache changes (a patch, or a cache read again or rebuilt)."""
    version = inventory.version()
    if version is None or version != _scrapes["version"]:
        _scrapes.update(version=version, by_stem={}, costs={})
    kept = _scrapes["by_stem"]  # read once: the full-size worker in cardedit may reset it from another thread
    if bucket in kept:
        return kept[bucket]
    listing = inventory.cached(f"{scrape_plan.SCRAPES}/{bucket}/")
    if listing is None:
        return None
    by_stem = scrape_plan.scrape_index(listing)
    if version is not None:
        kept[bucket] = by_stem
    return by_stem


def scrape_costs(layout, system, rels, by_stem):
    """{ROM path in the system folder: scrape bytes} for many ROMs, from the system's scrapes index (_scrapes_by_stem),
    built once so no scrape_cost call parses the listing again."""
    return {rel: scrape_plan.scrape_cost(layout, system, rel, {}, index=by_stem) for rel in rels}


def game_costs(card, system, keys):
    """({key: ROM bytes + scrape bytes} for the keys in the system's size cache, partial). A Vita game's ROM bytes
    include its DLC and newest update, unless those are keys themselves. partial: the system's sizes, or the scrape
    sizes the layout needs, aren't cached yet. Once they are, a key left out isn't in storage: it costs nothing."""
    bucket = system["bucket"]
    sizes = inventory.cached(f"{bucket}/")
    partial = sizes is None and bool(keys)
    sizes = sizes or {}
    layout = card.get("layout")
    sized = [k for k in keys if k in sizes]
    extras = vita.extras(sized, sizes)
    listed = set(sized)
    roms = {k: sizes[k] + sum(sizes[e] for e in extras.get(k, ()) if e not in listed) for k in sized}
    if layout not in scrape_plan.SCRAPE_LAYOUTS or not keys:
        return roms, partial
    scrapes = _scrapes_by_stem(bucket)
    if scrapes is None:
        return roms, True
    rels = [k[len(bucket) + 1:] for k in sized]
    # kept for the cache version, so a recount after a change prices only ROMs it hasn't seen (scrape_cost is slow)
    known = _scrapes["costs"].setdefault((layout, bucket), {}) if inventory.version() is not None else {}
    known.update(scrape_costs(layout, system, [r for r in rels if r not in known], scrapes))
    return {k: roms[k] + known[k[len(bucket) + 1:]] for k in sized}, partial


def _merged(card, systems, sets):
    """{system bucket: its store.merge_lists entry} of the card's games and the sets they reference, expanded once."""
    return {s["bucket"]: s for s in store.merge_lists([{"bucket": s["bucket"]} for s in systems], [card.get("games") or {}], sets)}


def _system_keys(card, system, games, collections_by_id):
    """The keys the card syncs of a system (games: its _merged entry), or None for a full system whose sizes aren't
    cached yet."""
    bucket = system["bucket"]
    if games["full_system"]:
        sizes = inventory.cached(f"{bucket}/")
        if sizes is None:
            return None
        return sorted(k for k in sizes if not k.endswith("/"))  # sync installs every file: exclusions don't apply
    skip = (card.get("excluded") or {}).get(bucket, ())
    keys = [g["bucket"] for g in games["games"] if g.get("bucket") and g["bucket"] not in skip]
    keys += [g["bucket"] for g in store.card_locked_games(card, collections_by_id).get(bucket, ())
             if g["bucket"] not in keys]  # collection games ignore exclusions
    return keys


def _system_usage(card, system, games, collections_by_id):
    keys = _system_keys(card, system, games, collections_by_id)
    if keys is None:
        return Usage(0, 0, True)
    if not keys:
        return Usage(0, 0, False)  # nothing picked: nothing to size
    costs, partial = game_costs(card, system, keys)
    return Usage(sum(costs.values()), len(keys), partial)  # count includes picked games not in storage


def _collections_by_id():
    return {c["id"]: c for c in colls.load_collections()}


def system_usage(card, system):
    """Usage of one system on a card: its direct picks, set references and full system, minus the card's exclusions
    (a full system ignores them, as sync does). Sizes not cached yet count as 0 and make the usage partial; a picked
    game not in storage (absent from a cached listing) counts as 0 and is not partial; a system with nothing picked is
    0 and not partial."""
    return _system_usage(card, system, _merged(card, [system], store.load_sets())[system["bucket"]], _collections_by_id())


def system_usages(card, systems):
    """{system bucket: Usage} for each of the systems (the sets are read and expanded once)."""
    merged, by_id = _merged(card, systems, store.load_sets()), _collections_by_id()
    return {s["bucket"]: _system_usage(card, s, merged[s["bucket"]], by_id) for s in systems}


def fetch_bytes(system, keys, to_fetch):
    """ROM bytes of the keys (and a Vita game's extras) that to_fetch(system, keys) says aren't on the card yet,
    from the size cache."""
    if not keys:
        return 0
    sizes = inventory.cached(f"{system['bucket']}/") or {}
    keys = list(keys)
    keys += [e for k in vita.extras(keys, sizes).values() for e in k if e not in keys]
    return sum(sizes.get(k, 0) for k in to_fetch(system, keys))


def card_fetch_bytes(card, systems, to_fetch):
    """fetch_bytes over every system the card syncs: how much of its ROMs a sync would download."""
    merged, by_id = _merged(card, systems, store.load_sets()), _collections_by_id()
    return sum(fetch_bytes(s, _system_keys(card, s, merged[s["bucket"]], by_id), to_fetch) for s in systems)


def bios_usage(systems):
    """Bytes of the BIOS files the systems need (each file once), from the BIOS/ cache; count is how many are in
    storage. Partial while BIOS/ isn't cached. A file not in storage costs nothing."""
    files = {f for s in systems for k in ("files", "rom_files") for f in (s.get("bios") or {}).get(k, [])}
    if not files:
        return Usage(0, 0, False)
    sizes = inventory.cached("BIOS/")
    if sizes is None:
        return Usage(0, 0, True)
    keys = [k for k in (f"BIOS/{f}" for f in files) if k in sizes]
    return Usage(sum(sizes[k] for k in keys), len(keys), False)


def full_usage(card, system):
    """Usage of a system on the card as a full system, whatever is picked: every file in its folder with the scrapes
    the card's layout installs, plus the system's own BIOS. count is its files. Partial while any of them isn't cached."""
    keys = _system_keys(card, system, {"full_system": True}, None)
    bios = bios_usage([system])
    if keys is None:
        return Usage(bios.bytes, 0, True)
    costs, partial = game_costs(card, system, keys)
    return Usage(sum(costs.values()) + bios.bytes, len(keys), partial or bios.partial)


def picked(usage):
    """Whether a system's Usage means the card syncs something of it (a full system not sized yet counts)."""
    return bool(usage.count or usage.partial)


def card_usage(card, systems, usages=None):
    """The card's total: every system's usage plus the BIOS of the systems with something picked. count is games only.
    usages: system_usages(card, systems) when already worked out."""
    usages = system_usages(card, systems) if usages is None else usages
    parts = [usages[s["bucket"]] for s in systems]
    bios = bios_usage([s for s in systems if picked(usages[s["bucket"]])])
    return Usage(sum(p.bytes for p in parts) + bios.bytes, sum(p.count for p in parts),
                 bios.partial or any(p.partial for p in parts))


def parse_size(text):
    """A card size as written to cards.json ("512 GB", "1 TB") from "512", "512gb", "1 TB"; None when it isn't one."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(GB|TB|G|T)?\s*", text, re.I)
    if not m or float(m.group(1)) <= 0:
        return None
    number = m.group(1).rstrip("0").rstrip(".") if "." in m.group(1) else m.group(1)
    return f"{number} {'TB' if (m.group(2) or 'GB').upper().startswith('T') else 'GB'}"


def card_capacity(card):
    """The card's size in bytes, or None when it has none or it isn't a size."""
    size = card.get("size")
    size = parse_size(size) if isinstance(size, str) else None
    if not size:
        return None
    number, unit = size.split()
    return int(float(number) * (10 ** 12 if unit == "TB" else 10 ** 9))

"""How much of a card's space its games take: ROM files plus the scraped files its layout installs, from the size cache."""
import os
from collections import defaultdict, namedtuple

from . import collections as colls, commands, inventory, scrape_plan, store

Usage = namedtuple("Usage", "bytes count partial")


def scrape_costs(layout, system, rels, listing):
    """{ROM path in the system folder: scrape bytes} for many ROMs, the listing split by ROM first so each
    scrape_cost call only sees that ROM's files."""
    by_stem = defaultdict(dict)
    for key, size in listing.items():
        entry = scrape_plan._index_entry(key)
        if entry:
            by_stem[entry[0]][key] = size
    return {rel: scrape_plan.scrape_cost(layout, system, rel, by_stem.get(os.path.splitext(rel)[0], {})) for rel in rels}


def game_costs(card, system, keys):
    """({key: ROM bytes + scrape bytes} for the keys in the system's size cache, partial). partial: the system's
    sizes, or the scrape sizes the layout needs, aren't cached yet. Once they are, a key left out isn't in storage:
    it costs nothing."""
    bucket = system["bucket"]
    sizes = inventory.cached(f"{bucket}/")
    partial = sizes is None and bool(keys)
    sizes = sizes or {}
    layout = card.get("layout")
    sized = [k for k in keys if k in sizes]
    if layout not in scrape_plan.SCRAPE_LAYOUTS or not keys:
        return {k: sizes[k] for k in sized}, partial
    scrapes = inventory.cached(f"{scrape_plan.SCRAPES}/{bucket}/")
    if scrapes is None:
        return {k: sizes[k] for k in sized}, True
    extra = scrape_costs(layout, system, [k[len(bucket) + 1:] for k in sized], scrapes)
    return {k: sizes[k] + extra[k[len(bucket) + 1:]] for k in sized}, partial


def _system_usage(card, system, sets, collections_by_id):
    bucket = system["bucket"]
    games = store.merge_lists([{"bucket": bucket}], [card.get("games") or {}], sets)[0]
    if games["full_system"]:
        sizes = inventory.cached(f"{bucket}/")
        if sizes is None:
            return Usage(0, 0, True)
        keys = sorted(k for k in sizes if not k.endswith("/"))  # sync installs every file: exclusions don't apply
    else:
        skip = (card.get("excluded") or {}).get(bucket, ())
        keys = [g["bucket"] for g in games["games"] if g.get("bucket") and g["bucket"] not in skip]
        keys += [g["bucket"] for g in store.card_locked_games(card, collections_by_id).get(bucket, ())
                 if g["bucket"] not in keys]  # collection games ignore exclusions
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
    return _system_usage(card, system, store.load_sets(), _collections_by_id())


def system_usages(card, systems):
    """{system bucket: Usage} for each of the systems (the sets are read once)."""
    sets, by_id = store.load_sets(), _collections_by_id()
    return {s["bucket"]: _system_usage(card, s, sets, by_id) for s in systems}


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


def card_capacity(card):
    """The card's size in bytes, or None when it has none or it isn't a size."""
    size = card.get("size")
    size = commands.parse_size(size) if isinstance(size, str) else None
    if not size:
        return None
    number, unit = size.split()
    return int(float(number) * (10 ** 12 if unit == "TB" else 10 ** 9))

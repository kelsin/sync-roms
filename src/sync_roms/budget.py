"""How much of a card's space its games take: ROM files plus the scraped files its layout installs, from the size cache."""
from collections import namedtuple

from . import commands, scrape_plan, sizecache, store

Usage = namedtuple("Usage", "bytes count partial")


def _system_usage(card, system, sets):
    bucket = system["bucket"]
    games = store.merge_lists([{"bucket": bucket}], [card.get("games") or {}], sets)[0]
    sizes = sizecache.cached(f"{bucket}/")
    partial = sizes is None
    sizes = sizes or {}
    if games["full_system"]:
        keys = sorted(k for k in sizes if not k.endswith("/"))
    else:
        keys = [g["bucket"] for g in games["games"] if g.get("bucket")]
    skip = (card.get("excluded") or {}).get(bucket, ())
    keys = [k for k in keys if k not in skip]
    layout = card.get("layout")
    scrapes = sizecache.cached(f"{scrape_plan.SCRAPES}/{bucket}/") if layout in scrape_plan.SCRAPE_LAYOUTS and keys else None
    if scrapes is None and layout in scrape_plan.SCRAPE_LAYOUTS and keys:
        partial = True
    total = 0
    for key in keys:
        if key in sizes:
            total += sizes[key]
        else:
            partial = True
        if scrapes:
            total += scrape_plan.scrape_cost(layout, system, key[len(bucket) + 1:], scrapes)
    return Usage(total, len(keys), partial)


def system_usage(card, system):
    """Usage of one system on a card: its direct picks, set references and full system, minus the card's exclusions.
    Sizes not cached yet count as 0 and make the usage partial."""
    return _system_usage(card, system, store.load_sets())


def card_usage(card, systems):
    sets = store.load_sets()
    parts = [_system_usage(card, s, sets) for s in systems]
    return Usage(sum(p.bytes for p in parts), sum(p.count for p in parts), any(p.partial for p in parts))


def card_capacity(card):
    """The card's size in bytes, or None when it has none or it isn't a size."""
    size = card.get("size")
    size = commands.parse_size(size) if isinstance(size, str) else None
    if not size:
        return None
    number, unit = size.split()
    return int(float(number) * (10 ** 12 if unit == "TB" else 10 ** 9))

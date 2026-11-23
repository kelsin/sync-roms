"""Guest cards: a friend's card that sync only adds to. Pure helpers for what sync recognizes, seeds and deletes."""
import os
import re
import xml.etree.ElementTree as ET

from . import cardfs, downloads, m3u, store


def is_guest(entry):
    return isinstance(entry, dict) and entry.get("guest") is True


def recognized(dest, keys, sizes, disc_dir=None, folders=None):
    """{storage key: card path as spelled on the card} for keys whose current file is on the card under a matching name."""
    walks = list(downloads.walk_roms(dest, rename_temps=True))
    if disc_dir:
        walks += downloads.walk_roms(os.path.join(dest, disc_dir), rename_temps=True)
    on_card = {}
    for root, files in walks:
        for f in files:
            path = os.path.join(root, f)
            on_card.setdefault(downloads.name_key(os.path.relpath(path, dest)), path)
    discs = m3u.disc_keys(keys) if disc_dir else ()
    out = {}
    for k in keys:
        path = on_card.get(downloads.name_key(downloads.rom_rel(k, disc_dir, discs, folders)))
        if path and downloads.is_current(path, sizes.get(k), disc_dir):
            out[k] = path
    return out


def seed_games(seed):
    """The cards.json `games` value for a seed {bucket: {key: card path}}."""
    return store.sorted_list({b: sorted(keys) for b, keys in seed.items() if keys})


def save_seed(card, seed):
    """Make the seed the card's picks in one write, dropping what would add to them; other fields stay."""
    cards = store.load_cards()
    entry = {k: v for k, v in cards.get(card, {}).items()
             if k not in ("excluded", "collections", "systems_off", "surprises")}
    entry["games"] = seed_games(seed)
    cards[card] = entry
    store.write_cards(cards)


def apply_seed(systems, seed):
    """In memory (dry runs): each system's games become the seed's."""
    for s in systems:
        s["games"] = [{"bucket": k, "title": store.key_title(k)} for k in sorted(seed.get(s["bucket"], {}))]
        s["full_system"] = False


def deletions(seed, picked, skipped):
    """Card paths of seeded ROMs no longer picked, leaving out the skipped buckets."""
    return sorted({path for b, keys in seed.items() if b not in skipped
                   for k, path in keys.items() if k not in picked.get(b, set())})


def new_files(jobs):
    """The jobs (key, path, size) whose file isn't on the card yet."""
    return [j for j in jobs if cardfs.size(j[1]) is None]


def new_gamelist_entries(gamelists):
    """{gamelist path: {rom rel: tags}} without the ROMs the file already lists."""
    out = {}
    for path, entries in gamelists.items():
        listed = set()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                m = re.search(r"<gameList\b.*</gameList>", f.read(), re.S)
            if m:
                listed = {(g.findtext("path") or "").strip() for g in ET.fromstring(m.group(0)).findall("game")}
        fresh = {rom: tags for rom, tags in entries.items() if "./" + rom not in listed}
        if fresh:
            out[path] = fresh
    return out

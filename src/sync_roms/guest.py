"""Guest cards: a friend's card that sync only adds to. Pure helpers for what sync recognizes, seeds and deletes."""
import os
import re
import xml.etree.ElementTree as ET

from . import cardfs, downloads, m3u, store, ui


def is_guest(entry):
    return isinstance(entry, dict) and entry.get("guest") is True


def named(dest, keys, disc_dir=None, folders=None):
    """{storage key: card path as spelled on the card} for keys with a file on the card under a matching name (case and
    Unicode form left out), whatever its size."""
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
        if path:
            out[k] = path
    return out


def recognized(dest, keys, sizes, disc_dir=None, folders=None):
    """{storage key: card path as spelled on the card} for keys whose current file is on the card under a matching name."""
    return {k: path for k, path in named(dest, keys, disc_dir, folders).items()
            if downloads.is_current(path, sizes.get(k), disc_dir)}


def seed_games(seed):
    """The cards.json `games` value for a seed {bucket: {key: card path}}."""
    return store.sorted_list({b: [{"bucket": k, "title": store.key_title(k)} for k in sorted(keys)]
                              for b, keys in seed.items() if keys})


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
    """Card paths of seeded ROMs no longer picked, leaving out the skipped buckets and any path a kept key was found at
    (systems that share a folder)."""
    kept = {path for b, keys in seed.items() for k, path in keys.items() if b in skipped or k in picked.get(b, set())}
    return sorted({path for b, keys in seed.items() if b not in skipped
                   for k, path in keys.items() if k not in picked.get(b, set())} - kept)


def new_files(jobs):
    """The jobs (key, path, size) whose file isn't on the card yet."""
    return [j for j in jobs if cardfs.size(j[1]) is None]


def new_gamelist_entries(gamelists):
    """{gamelist path: {rom rel: tags}} without the ROMs the file already lists. A file that is there but doesn't
    parse is left out, with a warning: writing it would replace the friend's whole list."""
    out = {}
    for path, entries in gamelists.items():
        listed = set()
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                # as scrape_plan.update_gamelist finds it
                m = re.search(r"<gameList\b[^>]*/>", text) or re.search(r"<gameList\b.*</gameList>", text, re.S)
                if not m:
                    raise ValueError("no <gameList>")
                listed = {downloads.name_key((g.findtext("path") or "").strip())
                          for g in ET.fromstring(m.group(0)).findall("game")}
            except (ET.ParseError, OSError, UnicodeDecodeError, ValueError) as e:
                ui.warn(f"{path} doesn't parse ({e}): left as it is")
                continue
        fresh = {rom: tags for rom, tags in entries.items() if downloads.name_key("./" + rom) not in listed}
        if fresh:
            out[path] = fresh
    return out

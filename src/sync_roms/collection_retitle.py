"""`sync-roms collections retitle`: make each collection game's stored title the scraped name."""
from . import collections, names, s3, scrape_plan, ui


def retitle(dry_run=False):
    """Set every collection game's title to its scraped name (else `names.title`), rewriting only the collections where
    one changed. Returns the number of games changed. Fails (exit 1) when storage's metadata can't be read."""
    loaded = collections.load_collections()
    systems = sorted({g["bucket"].partition("/")[0] for c in loaded for g in c["games"]})
    try:
        s3.check_root()
        metadata = {system: scrape_plan.load_metadata(system) for system in systems}
    except (ValueError, *s3.ERRORS) as e:
        ui.fail(f"Couldn't read the scraped names from storage: {e}", 1)
    changed = 0
    for collection in loaded:
        count = 0
        for game in collection["games"]:
            new = names.scraped_name(metadata, game["bucket"]) or names.title(game["bucket"])
            old = game.get("title")
            if old == new:
                continue
            print(f"{collection['name']} ({game['system']}): {old if isinstance(old, str) and old else '(none)'} -> {new}")
            game["title"] = new
            count += 1
        if count and not dry_run:
            collections.save_collection(collection)
        changed += count
    print(f"{'Would retitle' if dry_run else 'Retitled'} {changed} game(s).")
    return changed

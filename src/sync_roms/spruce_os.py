"""The newest spruceOS release 7z from storage's os/spruceos/, staged at the card root for the device's EZ Updater."""
import contextlib
import os
import re

from . import inventory, onion_surprise, runtime, s3, store, ui

PATTERN = r"spruceV\d+(\.\d+)*\.7z"


def newest(listing):
    """The storage key of the newest spruceOS release 7z in the listing (digit runs compared as numbers), or None."""
    prefix = runtime.SPRUCE_PREFIX
    keys = [k for k in listing if k.startswith(prefix) and re.fullmatch(PATTERN, k[len(prefix):])]
    return max(keys, key=lambda k: onion_surprise._natural(k[len(prefix):]), default=None)


def install(card, layout_name, base, dry_run):
    """Put the newest spruceOS 7z at the root of a spruce card, once per file name. The failure count."""
    if layout_name != "spruce":
        return 0
    listing = inventory.files(runtime.SPRUCE_PREFIX)
    key = newest(listing)
    if not key:
        return 0
    name = key[len(runtime.SPRUCE_PREFIX):]
    entry = store.load_cards().get(card)
    old = entry.get("spruce_os") if isinstance(entry, dict) else None
    if old == name:
        return 0
    if dry_run:
        print(ui.dim(f"🧪 Dry run: would stage spruceOS {name} at the card root"))
        return 0
    target = os.path.join(base, name)
    try:
        if not (os.path.isfile(target) and os.path.getsize(target) == listing[key]):
            s3.download((key, target, listing[key]))
    except (OSError, *s3.ERRORS) as e:
        ui.warn(f"Couldn't stage spruceOS {name} on the card: {e}")
        return 1
    if isinstance(old, str) and old != name and re.fullmatch(PATTERN, old):
        previous = os.path.join(base, old)
        if os.path.isfile(previous):
            with contextlib.suppress(OSError):
                os.remove(previous)
    store.update_card(card, spruce_os=name)
    print(f"🌲 spruceOS {ui.green(name)} → card root (run Apps → EZ Updater on the device)")
    return 0

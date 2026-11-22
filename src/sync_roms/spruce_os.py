"""The newest spruceOS release 7z from storage's os/spruceos/, staged at the card root for the device's EZ Updater."""
import contextlib
import os
import re

from . import downloads, inventory, runtime, store, ui

PATTERN = r"spruceV\d+(\.\d+)*\.7z"
MARGIN = 64 * 1024 * 1024  # room left on the card after the 7z


def install(card, layout_name, base, dry_run, wrote=None, keep=False):
    """Put the newest spruceOS 7z at the root of a spruce card, once per file name. The failure count.
    wrote, a list, gets the card path of the 7z when it was staged. keep (--no-delete): leave the previous one."""
    if layout_name != "spruce":
        return 0
    listing = inventory.files(runtime.SPRUCE_PREFIX)
    key = inventory.newest(listing, runtime.SPRUCE_PREFIX, PATTERN)
    if not key:
        return 0
    name, size = key[len(runtime.SPRUCE_PREFIX):], listing[key]
    entry = store.load_cards().get(card)
    old = entry.get("spruce_os") if isinstance(entry, dict) else None
    if old == name:
        return 0
    previous = os.path.join(base, old) if isinstance(old, str) and re.fullmatch(PATTERN, old) else None
    previous = previous if previous and os.path.isfile(previous) else None
    shown = f"{name} ({ui.human_size(size)})"
    if dry_run:
        tail = f" (keeping {old}: --no-delete)" if previous and keep else f" and delete {old}" if previous else ""
        print(ui.dim(f"🧪 Dry run: would stage spruceOS {shown} at the card root{tail}"))
        return 0
    target = os.path.join(base, name)
    if not (os.path.isfile(target) and os.path.getsize(target) == size):
        free = downloads.free_space(base)
        if free < size + MARGIN:
            ui.warn(f"Not enough room to stage spruceOS {name}: it needs {ui.human_size(size + MARGIN)}, "
                    f"the card has {ui.human_size(free)} free")
            return 1
        print(f"🌲 Staging spruceOS {shown}…")
        failures = []
        if downloads.run_downloads([(key, target, size)], "spruceOS", "🌲", base, failures):
            ui.warn(f"Couldn't stage spruceOS {name} on the card: {failures[0][1]}")
            return 1
    if previous and keep:
        print(ui.dim(f"🔒 --no-delete: keeping the previous spruceOS {old}"))
    elif previous:
        with contextlib.suppress(OSError):
            os.remove(previous)
    if wrote is not None:
        wrote.append(target)
    store.update_card(card, spruce_os=name)
    print(f"🌲 spruceOS {ui.green(name)} → card root (run Apps → EZ Updater on the device)")
    return 0

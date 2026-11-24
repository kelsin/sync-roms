"""sync-roms unmount: tidy a mounted SD card the way the end of a sync does, then unmount it."""
import sys

from . import clean, flash, picker, runtime, ui


def run(args):
    if sys.platform != "darwin":
        ui.failure(ui.red("❌ unmount needs macOS"))
        return 1
    exclude = flash.disks_of(runtime.ROOT) if runtime.ROOT else set()  # never offer the disk holding storage
    cards = [d for d in flash.external_disks(exclude) if d.mounts]
    if not cards:
        ui.failure(ui.red("❌ no mounted SD card found"))
        return 1
    i = picker.filter_list("🃏 Which card?", [flash._disk_label(d) for d in cards], hint=flash.HINT)
    if i is None:
        return 0
    disk = cards[i]
    if args.dry_run:
        print(f"Would tidy {', '.join(disk.mounts)} and unmount {disk.id}")
        return 0
    try:
        for mount in disk.mounts:
            clean._clean_root = mount
            clean.clean_dirs()
        clean._clean_root = None
        clean._eject_root = disk.mounts[0]
        return 0 if clean.eject() else 1
    finally:  # cli.main's own end-of-run tidy and eject must find nothing left to do
        clean._clean_root = clean._eject_root = None

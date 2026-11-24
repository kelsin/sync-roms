"""sync-roms mount: mount again an SD card that was unmounted (by unmount or the end of a sync) but not pulled."""
import subprocess
import sys

from . import flash, picker, runtime, ui


def run(args):
    if sys.platform != "darwin":
        ui.failure(ui.red("❌ mount needs macOS"))
        return 1
    exclude = flash.disks_of(runtime.ROOT) if runtime.ROOT else set()  # never offer the disk holding storage
    cards = [d for d in flash.external_disks(exclude) if not d.mounts]
    if not cards:
        ui.failure(ui.red("❌ no unmounted SD card found"))
        return 1
    i = picker.filter_list("🃏 Which card?", [flash._disk_label(d) for d in cards], hint=flash.HINT)
    if i is None:
        return 0
    disk = cards[i]
    if args.dry_run:
        print(f"Would mount {disk.id}")
        return 0
    print(ui.bold(f"\n💾 Mounting {disk.id}..."))
    r = subprocess.run(["diskutil", "mountDisk", disk.id], capture_output=True, text=True)
    if r.returncode != 0:
        ui.failure(ui.red(f"❌ couldn't mount {disk.id}: {(r.stderr or r.stdout).strip()}"))
        return 1
    print(ui.green(f"✅ {r.stdout.strip()}"))
    return 0

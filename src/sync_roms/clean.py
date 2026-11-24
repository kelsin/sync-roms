"""Cleaning junk files off the card."""
import os
import plistlib
import shutil
import signal
import subprocess
import sys
import time

from . import ui


_clean_root = None
_eject_root = None  # the card to unmount once the run is over (see eject)
DELETE_RETRIES = 2
SKIPPED_FOLDERS = {".Spotlight-V100", ".fseventsd", ".Trashes"}  # macOS keeps these; no ._ files to delete in them


def delete_appledouble(path):
    """Delete every ._* file under path in one walk, except in the folders macOS keeps for itself. Returns the ones it couldn't delete."""
    left = []
    stack = [path]
    tty = sys.stdout.isatty()
    folders = deleted = 0
    drawn = False
    last = time.monotonic()
    while stack:
        folder = stack.pop()
        now = time.monotonic()
        if now - last >= (ui.POLL if tty else ui.PLAIN_INTERVAL):  # a big card takes minutes to walk: show it's moving
            last = now
            if tty:
                line = f"  🧼 {folders:,} folders · {deleted:,} ._ deleted · {os.path.relpath(folder, path)}"
                sys.stdout.write("\r\033[J" + ui.cut_cells(line, shutil.get_terminal_size().columns - 1))  # never wraps, so \r redraws it
                sys.stdout.flush()
                drawn = True
            else:
                print(f"progress: {folders} folders checked, {deleted} ._ file(s) deleted")
        folders += 1
        try:
            with os.scandir(folder) as it:
                entries = list(it)
        except OSError:
            continue
        for e in entries:
            if e.is_dir(follow_symlinks=False):
                if e.name not in SKIPPED_FOLDERS:
                    stack.append(e.path)
            elif e.name.startswith("._"):
                try:
                    os.remove(e.path)
                    deleted += 1
                except OSError:
                    left.append(e.path)
    if drawn:
        sys.stdout.write("\r\033[J")
    print(f"  {'❌' if left else '✅'} {path}" + (ui.dim(f" ({len(left)} ._ file(s) left)") if left else ""))
    return left


def remove_left(paths):
    """Delete the ._* files an earlier pass couldn't delete (paths) and return the ones still there, without walking the card again."""
    for path in paths:
        try:
            os.remove(path)
        except OSError:
            pass
    left = [p for p in paths if os.path.lexists(p)]
    print(f"  {'❌' if left else '✅'} removed {len(paths) - len(left)} of {len(paths)}")
    return left


def quiet_fseventsd(root):
    """Empty the root's .fseventsd folder (macOS's file event log) and add .fseventsd/no_log so it isn't written again (nothing to do once it is there)."""
    log_dir = os.path.join(root, ".fseventsd")
    if os.path.lexists(os.path.join(log_dir, "no_log")):
        return
    try:
        os.makedirs(log_dir, exist_ok=True)
        for name in os.listdir(log_dir):
            path = os.path.join(log_dir, name)
            if name != "no_log" and os.path.isfile(path):
                os.remove(path)
        open(os.path.join(log_dir, "no_log"), "a").close()
    except OSError as e:
        print(ui.yellow(f"  ⚠️  Couldn't clean .fseventsd in {root}: {e}"))


def clean_dirs():
    """Mark the root folder as not to be indexed, then delete macOS AppleDouble (._*) files under it (macOS only).

    ^C skips the rest of the cleaning (it can be done by running sync again).
    """
    if not _clean_root:
        return
    print(ui.bold(f"\n🏁 Finalizing card {_clean_root} (^C skips this)..."))
    try:
        _clean_card()
    except KeyboardInterrupt:
        print(ui.yellow("\n↩️  Skipped the rest of the card cleaning"))


def spotlight_active(path):
    """True when Spotlight is indexing path or has left an index on it (macOS creates ._ files while it does)."""
    if os.path.exists(os.path.join(path, ".Spotlight-V100")):
        return True
    r = subprocess.run(["mdutil", "-s", path], capture_output=True, text=True)
    return "Indexing enabled" in r.stdout


def _stop_indexing(root):
    """Turn Spotlight indexing off for the card and delete its index, if it is on (needs sudo, so asks first)."""
    if not shutil.which("mdutil") or not spotlight_active(root):
        return
    cmd = f"sudo mdutil -i off {root} && sudo mdutil -X {root}"
    ask = not ui.ASSUME_YES and sys.stdin.isatty()
    print(ui.bold(f"\n🔍 Spotlight is indexing the card, which keeps recreating ._ files. Turning it off needs: {cmd}"),
          file=sys.stderr if ask and ui.QUIET else sys.stdout)  # under --quiet the question is on stderr: show what it runs there too
    if not ask:
        print(ui.yellow("  ↩️  Not asking for sudo's password here: run that command yourself if you want it"))
    elif ui.confirm("Run it now? (sudo asks for your password)"):
        # sudo needs ^C to work at its password prompt
        default_sigint = lambda: signal.signal(signal.SIGINT, signal.SIG_DFL)
        for args in (["-i", "off"], ["-X"]):
            r = subprocess.run(["sudo", "mdutil", *args, root], preexec_fn=default_sigint)
            if r.returncode != 0:
                ui.failure(ui.red(f"  ❌ sudo mdutil {' '.join(args)} failed ({r.returncode})"))


def _clean_card():
    marker = os.path.join(_clean_root, ".metadata_never_index")
    try:  # on any OS: it keeps Spotlight from indexing the card when it is next used on a Mac
        if not os.path.lexists(marker):
            open(marker, "a").close()
    except OSError as e:
        print(ui.yellow(f"  ⚠️  Couldn't create .metadata_never_index in {_clean_root}: {e}"))
    quiet_fseventsd(_clean_root)
    if sys.platform != "darwin":
        return
    _stop_indexing(_clean_root)
    print(ui.bold("\n🧼 Deleting ._ files..."))
    left = delete_appledouble(_clean_root)
    # A first pass often leaves files behind (the card is still settling); deleting those a moment later
    # usually finishes the job.
    for _ in range(DELETE_RETRIES):
        if not left:
            break
        time.sleep(2)
        print(ui.bold(f"\n🧼 Removing the {len(left)} ._ file(s) left..."))
        left = remove_left(left)
    if left:
        ui.failure(ui.red(f"\n⚠️  {len(left)} ._ file(s) are still there after deleting:"))
        for path in left[:10]:
            ui.failure(ui.dim(f"     {path}"))
        if len(left) > 10:
            ui.failure(ui.dim(f"     … and {len(left) - 10} more"))


def card_disk(path):
    """The whole disk (e.g. disk4) holding path when it is removable or external media, else None (the boot disk, a network share)."""
    mount = os.path.realpath(path)
    while not os.path.ismount(mount):
        mount = os.path.dirname(mount)
    if mount == "/":
        return None
    r = subprocess.run(["diskutil", "info", "-plist", mount], capture_output=True)
    if r.returncode != 0:
        return None
    info = plistlib.loads(r.stdout)
    if not (info.get("RemovableMediaOrExternalDevice") or info.get("Ejectable") or info.get("Removable")):
        return None
    return info.get("ParentWholeDisk") or None


def volume_device(path):
    """The device identifier (e.g. disk5s1) of the volume holding path, for diskutil repairVolume; None off macOS, on
    the boot volume or when diskutil can't say."""
    if sys.platform != "darwin" or not shutil.which("diskutil"):
        return None
    mount = os.path.realpath(path)
    while not os.path.ismount(mount):
        mount = os.path.dirname(mount)
    if mount == "/":
        return None
    r = subprocess.run(["diskutil", "info", "-plist", mount], capture_output=True)
    if r.returncode != 0:
        return None
    return plistlib.loads(r.stdout).get("DeviceIdentifier") or None


def eject():
    """Unmount every volume on the card's disk with diskutil unmountDisk (macOS only), so it can be pulled right away.

    True when it unmounted or had nothing to do, False when diskutil failed."""
    if not _eject_root or sys.platform != "darwin" or not shutil.which("diskutil"):
        return True
    disk = card_disk(_eject_root)
    if not disk:  # a folder on this Mac's own disk or a share: nothing to pull out
        return True
    os.chdir("/")  # sync-roms's own working directory on the card would keep it busy
    print(ui.bold(f"\n⏏️  Unmounting {disk}..."))
    r = subprocess.run(["diskutil", "unmountDisk", disk], capture_output=True, text=True)
    if r.returncode == 0:
        print(ui.green("  ✅ Safe to remove the card"))
        return True
    else:
        ui.failure(ui.red(f"  ❌ {(r.stderr or r.stdout).strip()}"))
        ui.failure(ui.dim(f"     A shell or app with the card open keeps it busy: close it, then run diskutil unmountDisk {disk}"))
    return False

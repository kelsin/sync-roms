"""Cleaning junk files and Android media folders off the card."""
import os
import plistlib
import shutil
import signal
import subprocess
import sys
import time

from . import store, ui


_clean_root = None
_eject_root = None  # the card to unmount once the run is over (see eject)
DOT_CLEAN_RETRIES = 2


def dot_clean(path):
    """Run dot_clean on path (always delete ._ files, even orphans, without merging their attributes), which should delete every ._* file. Returns (exit ok, ._* files still there)."""
    r = subprocess.run(["dot_clean", "-mn", "--keep=native", path], capture_output=True, text=True)
    # dot_clean exits 0 even when a merge fails, so also look for ._* files it left behind
    left = [os.path.join(root, f) for root, _, files in os.walk(path) for f in files if f.startswith("._")]
    ok = r.returncode == 0 and not left
    print(f"  {'✅' if ok else '❌'} {path}"
          + (ui.dim(f" ({len(left)} ._ file(s) left)") if left else "")
          + ("" if r.returncode == 0 else ui.red(f": {r.stderr.strip()}")))
    return r.returncode == 0, left


ANDROID_MEDIA_DIRS = ("Alarms", "Audiobooks", "DCIM", "Documents", "Download", "Movies", "Music",
                      "Notifications", "Pictures", "Podcasts", "Recordings", "Ringtones")


def android_media_files(base):
    """{folder: files} for the Android media folders that exist in base (files other than .nomedia)."""
    found = {}
    for name in ANDROID_MEDIA_DIRS:
        folder = os.path.join(base, name)
        if os.path.isdir(folder):
            found[name] = [os.path.join(root, f) for root, _, files in os.walk(folder) for f in files if f != ".nomedia"]
    return found


def clean_android_media(base, card, dry_run, ask=False):
    """Empty the Android media folders on the card and put a .nomedia in each, as the card's saved setting says.

    The setting (android_media in cards.json) is "always" or "never" and is used without asking. Without
    one, ask when any of the folders has files, and remember the answer. Folders that don't exist are not
    created. With ask, the saved setting is confirmed first; declining it asks the question again and
    saves the new answer.
    """
    found = android_media_files(base)
    files = [f for fs in found.values() for f in fs]
    setting = (store.load_cards().get(card) or {}).get("android_media")
    redo = False
    if ask and not dry_run and setting in ("always", "never"):
        what = "remove the files in the Android media folders and add .nomedia" if setting == "always" else "leave the Android media folders alone"
        if not ui.confirm(f"Use the saved setting for {card}: {what}?"):
            setting, redo = None, True
    if not redo and (not found or setting == "never" or (setting != "always" and not files)):
        return
    counts = ", ".join(f"{name} ({len(fs)})" for name, fs in found.items() if fs)
    if dry_run:
        print(f"📵 Android media folders: {len(files)} file(s) would be removed and .nomedia added "
              f"({'setting: always' if setting == 'always' else 'would ask first'}){': ' + counts if counts else ''}")
        return
    if setting != "always":
        size = sum(os.path.getsize(f) for f in files if os.path.exists(f))
        print(ui.bold(f"\n📵 Android media folders on {card} have {len(files)} file(s) ({ui.human_size(size)})"
                   + (f": {counts}" if counts else "")))
        answer = ui.confirm("Remove them and add a .nomedia file to each folder? Your answer is remembered for this card name.",
                         default=False)
        store.update_card(card, android_media="always" if answer else "never")
        if not answer:
            print(ui.yellow("  ↩️  Keeping them (not asking again for this card)"))
            return
    removed = 0
    for path in files:
        try:
            os.remove(path)
            removed += 1
        except OSError as e:
            print(ui.red(f"  ❌ {path}: {e}"))
    for name in found:
        try:
            open(os.path.join(base, name, ".nomedia"), "a").close()
        except OSError as e:
            print(ui.red(f"  ❌ {name}/.nomedia: {e}"))
    print(ui.green(f"📵 Removed {removed} file(s) from the Android media folders and added .nomedia to {len(found)} folder(s)"))


def quiet_fseventsd(root):
    """Empty the root's .fseventsd folder (macOS's file event log) and add .fseventsd/no_log so it isn't written again."""
    log_dir = os.path.join(root, ".fseventsd")
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
    """Mark the root folder as not to be indexed, then merge/remove macOS AppleDouble (._*) files under it (macOS only).

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
    print(ui.bold(f"\n🔍 Spotlight is indexing the card, which keeps recreating ._ files. Turning it off needs: {cmd}"))
    if ui.ASSUME_YES or not sys.stdin.isatty():
        print(ui.yellow("  ↩️  Not asking for sudo's password here: run that command yourself if you want it"))
    elif ui.confirm("Run it now? (sudo asks for your password)"):
        # sudo needs ^C to work at its password prompt
        default_sigint = lambda: signal.signal(signal.SIGINT, signal.SIG_DFL)
        for args in (["-i", "off"], ["-X"]):
            r = subprocess.run(["sudo", "mdutil", *args, root], preexec_fn=default_sigint)
            if r.returncode != 0:
                print(ui.red(f"  ❌ sudo mdutil {' '.join(args)} failed ({r.returncode})"))


def _clean_card():
    try:  # on any OS: it keeps Spotlight from indexing the card when it is next used on a Mac
        open(os.path.join(_clean_root, ".metadata_never_index"), "a").close()
    except OSError as e:
        print(ui.yellow(f"  ⚠️  Couldn't create .metadata_never_index in {_clean_root}: {e}"))
    quiet_fseventsd(_clean_root)
    if not shutil.which("dot_clean"):
        return
    _stop_indexing(_clean_root)
    print(ui.bold("\n🧼 Running dot_clean..."))
    ok, left = dot_clean(_clean_root)
    # A first pass often leaves files behind (the card is still settling); another pass usually finishes
    # the job.
    for _ in range(DOT_CLEAN_RETRIES):
        if ok and not left:
            break
        time.sleep(2)
        print(ui.bold("\n🧼 Retrying dot_clean..."))
        ok, left = dot_clean(_clean_root)
    if left:
        print(ui.red(f"\n⚠️  {len(left)} ._ file(s) are still there after dot_clean:"))
        for path in left[:10]:
            print(ui.dim(f"     {path}"))
        if len(left) > 10:
            print(ui.dim(f"     … and {len(left) - 10} more"))


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


def eject():
    """Unmount every volume on the card's disk with diskutil unmountDisk (macOS only), so it can be pulled right away."""
    if not _eject_root or sys.platform != "darwin" or not shutil.which("diskutil"):
        return
    disk = card_disk(_eject_root)
    if not disk:  # a folder on this Mac's own disk or a share: nothing to pull out
        return
    os.chdir("/")  # sync-roms's own working directory on the card would keep it busy
    print(ui.bold(f"\n⏏️  Unmounting {disk}..."))
    r = subprocess.run(["diskutil", "unmountDisk", disk], capture_output=True, text=True)
    if r.returncode == 0:
        print(ui.green("  ✅ Safe to remove the card"))
    else:
        print(ui.red(f"  ❌ {(r.stderr or r.stdout).strip()}"))
        print(ui.dim(f"     A shell or app with the card open keeps it busy: close it, then run diskutil unmountDisk {disk}"))

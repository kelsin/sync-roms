"""Cleaning junk files and Android media folders off the card."""
import os
import shutil
import signal
import subprocess

from . import store, ui


_clean_root = None


def dot_clean(path):
    """Run dot_clean -m on path, which should delete every ._* file. Returns (exit ok, ._* files still there)."""
    r = subprocess.run(["dot_clean", "-m", path], capture_output=True, text=True)
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
    """Mark the root folder as not to be indexed, then merge/remove macOS AppleDouble (._*) files under it (macOS only)."""
    if not _clean_root:
        return
    try:  # on any OS: it keeps Spotlight from indexing the card when it is next used on a Mac
        open(os.path.join(_clean_root, ".metadata_never_index"), "a").close()
    except OSError as e:
        print(ui.yellow(f"  ⚠️  Couldn't create .metadata_never_index in {_clean_root}: {e}"))
    quiet_fseventsd(_clean_root)
    if not shutil.which("dot_clean"):
        return
    print(ui.bold("\n🧼 Running dot_clean..."))
    ok, left = dot_clean(_clean_root)
    if not ok or left:
        print(ui.bold(f"\n🔍 dot_clean couldn't clean everything, turning Spotlight indexing off for {_clean_root} (sudo may ask for your password)..."))
        # sudo needs ^C to work at its password prompt, but main() ignores SIGINT for dot_clean
        default_sigint = lambda: signal.signal(signal.SIGINT, signal.SIG_DFL)
        for args in (["-i", "off"], ["-X"]):
            r = subprocess.run(["sudo", "mdutil", *args, _clean_root], preexec_fn=default_sigint)
            if r.returncode != 0:
                print(ui.red(f"  ❌ sudo mdutil {' '.join(args)} failed ({r.returncode})"))
        print(ui.bold("\n🧼 Retrying dot_clean..."))
        _, left = dot_clean(_clean_root)
    if left:
        print(ui.red(f"\n⚠️  {len(left)} ._ file(s) are still there after dot_clean:"))
        for path in left[:10]:
            print(ui.dim(f"     {path}"))
        if len(left) > 10:
            print(ui.dim(f"     … and {len(left) - 10} more"))

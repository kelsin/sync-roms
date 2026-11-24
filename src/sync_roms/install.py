"""`cards install`: a fresh spruceOS on a card. Everything at the card root but its ROMs, BIOS, saves and storage's
themes is deleted, then storage's newest spruceOS 7z is unpacked onto it without replacing the files kept."""
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata

from . import convert, downloads, external, flash, inventory, runtime, saves, spruce_os, spruce_themes, store, ui

KEEP = frozenset({"roms", "bios", "saves", "themes", ".spotlight-v100", ".trashes", ".fseventsd",
                  "system volume information"})


def _kept(name):
    return name.lower() in KEEP or name.startswith("._")


def theme_key(name):
    """A theme folder name compared ignoring case and Unicode form (a card can hold an NFD name, storage an NFC one)."""
    return unicodedata.normalize("NFC", name).lower()


def _mounted(path):
    return os.path.ismount(path)


def plan(base, themes):
    """(deleted, kept), sorted absolute paths: the root entries not kept and the Themes/ entries whose theme_key isn't
    in themes are deleted; the kept root entries and theme folders are kept."""
    deleted, kept = [], []
    for entry in os.scandir(base):
        if not _kept(entry.name):
            deleted.append(entry.path)
            continue
        kept.append(entry.path)
        if entry.name.lower() == "themes" and entry.is_dir(follow_symlinks=False):
            for theme in os.scandir(entry.path):
                (kept if theme_key(theme.name) in themes else deleted).append(theme.path)
    return sorted(deleted), sorted(kept)


def _size(path):
    if not os.path.isdir(path) or os.path.islink(path):
        return os.lstat(path).st_size
    return sum(os.lstat(os.path.join(d, f)).st_size for d, _, fs in os.walk(path) for f in fs)


def unpacked_size(archive):
    """The total unpacked bytes of a 7z, from its technical listing; None when 7z can't list it."""
    done = subprocess.run([external.find_tool("7z"), "l", "-slt", "--", archive], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, errors="replace")
    sizes = [int(line[len("Size = "):]) for line in done.stdout.splitlines()
             if line.startswith("Size = ") and line[len("Size = "):].strip().isdigit()]
    return sum(sizes) if done.returncode == 0 and sizes else None


def _run_7z(args, total):
    """Run 7z with args, its percent driving a progress bar by total (bytes). None on success, else the last line it
    printed on stderr; exit code 1 is a warning (e.g. attributes a FAT card can't keep), warned about and a success."""
    cmd = [external.find_tool("7z"), *args]
    percent = [0]
    bar = ui.ProgressBar(1, lambda: percent[0] / 100, total)
    with tempfile.TemporaryFile() as err:  # a file, not a pipe: 7z can't block on it while stdout is read
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err)
        try:
            tail = ""
            while chunk := proc.stdout.read1(4096):  # 7z redraws its percent with backspaces, not line ends
                tail = (tail + chunk.decode(errors="replace"))[-64:]
                found = re.findall(r"(\d+)%", tail)
                if found and int(found[-1]) != percent[0]:
                    percent[0] = int(found[-1])
                    bar.draw(0)
                    tail = ""
            proc.wait()
        except BaseException:  # the reader failed: 7z must not outlive this call
            proc.kill()
            proc.wait()
            raise
        finally:
            proc.stdout.close()
            bar.clear()
        if proc.returncode:
            err.seek(0)
            lines = [line.strip() for line in err.read().decode(errors="replace").splitlines() if line.strip()]
            last = lines[-1] if lines else f"exit code {proc.returncode}"
            if proc.returncode != 1:
                return last
            ui.warn(f"7z: {last}")
    return None


def check(archive, total):
    """Test every file in archive (7z t), with a progress bar by total (bytes): None when it is whole, else 7z's error."""
    return _run_7z(["t", "-bso0", "-bsp1", "--", archive], total)


def unpack(archive, base, total):
    """Unpack archive onto base, skipping the files base already has, with a progress bar by total (bytes). None on
    success, else the last line 7z printed on stderr."""
    return _run_7z(["x", "-y", "-aos", "-bso0", "-bsp1", f"-o{base}", "--", archive], total)


def run(args):
    """`cards install [CARD] [--dry-run] [--yes]`: install storage's newest spruceOS onto a spruce card."""
    base, name, (_, layout), _ = saves.card_setup(args)
    if not _mounted(base):
        ui.fail(f"{base} isn't a mounted card: cards install only runs on an SD card's root", 2)
    if layout != "spruce":
        ui.fail(f"cards install supports only spruce cards; {name} is {layout}", 2)
    listing = inventory.files(runtime.SPRUCE_PREFIX)
    key = inventory.newest(listing, runtime.SPRUCE_PREFIX, spruce_os.PATTERN)
    if not key:
        ui.failure(ui.red(f"❌ no spruceOS release ({runtime.SPRUCE_PREFIX}spruceV<version>.7z) in storage"))
        return 1
    release, size = key[len(runtime.SPRUCE_PREFIX):], listing[key]
    themes = {theme_key(n) for n in spruce_themes.available()}
    deleted, kept = plan(base, themes)
    if not themes and any(os.path.dirname(p) != base for p in deleted):
        ui.warn("storage has no spruce themes, so everything in Themes/ goes; run `sync-roms themes update` first to keep them")
    sizes = {path: _size(path) for path in deleted}
    print(ui.bold(f"{name}: install spruceOS {release} ({ui.human_size(size)})"))
    if kept:
        print(ui.dim("Kept: " + ", ".join(os.path.relpath(p, base) for p in kept)))
    if deleted:
        print(ui.bold("Deleted:"))
        for path in deleted:
            print(f"  {os.path.relpath(path, base)}  {ui.dim(ui.human_size(sizes[path]))}")
    if args.dry_run:
        print(ui.yellow("🧪 Dry run: nothing downloaded, deleted or unpacked"))
        return 0
    if not args.yes and not ui.has_terminal():
        ui.fail("Pass --yes to install without a terminal to confirm on", 2)
    if not external.find_tool("7z"):
        ui.fail("7z isn't installed, so spruceOS can't be unpacked; run `sync-roms tools install`", 3)
    tmp = tempfile.mkdtemp(prefix="sync-roms-install-")
    try:
        if shutil.disk_usage(tmp).free < size + flash.SPARE:
            ui.failure(ui.red(f"❌ not enough free space in {tempfile.gettempdir()} for {ui.human_size(size)}"))
            return 1
        archive = os.path.join(tmp, release)
        failures = []
        if downloads.run_downloads([(key, archive, size)], "spruceOS", "🌲", tmp, failures):
            ui.failure(ui.red(f"❌ couldn't download spruceOS {release}: {failures[0][1] if failures else 'failed'}"))
            return 1
        total = unpacked_size(archive)
        if total is None:
            ui.failure(ui.red(f"❌ 7z can't read the downloaded {release}: nothing deleted"))
            return 1
        print(f"🔍 Testing spruceOS {release}…")
        error = check(archive, total)
        if error:
            ui.failure(ui.red(f"❌ the downloaded {release} is damaged ({error}): nothing deleted"))
            return 1
        free = downloads.free_space(base) + sum(sizes.values())
        if free < total + spruce_os.MARGIN:
            ui.failure(ui.red(f"❌ not enough room on {name}: spruceOS needs {ui.human_size(total + spruce_os.MARGIN)}, "
                              f"the card would have {ui.human_size(free)} free"))
            return 1
        if not args.yes and not ui.confirm(f"Delete {len(deleted)} items from {base} and install spruceOS {release}?",
                                       default=False):
            return 1
        if deleted:
            step, bar = convert._progress(len(deleted))
            failed = convert.remove_media(deleted, base, step)
            bar.clear()
            if failed:
                for path, err in failed:
                    ui.warn(f"could not delete {path}: {err}")
                ui.failure(ui.red(f"❌ {len(failed)} deletion(s) failed; spruceOS not unpacked. Fix the cause and run install again"))
                return 3
        print(f"🌲 Unpacking spruceOS {release} ({ui.human_size(total)})…")
        error = unpack(archive, base, total)
        if error:
            ui.failure(ui.red(f"❌ could not unpack {release}: {error}. {name} has no spruceOS now: "
                              "run `sync-roms cards install` again"))
            return 3
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    cards = store.load_cards()
    entry = dict(store.saved_card(name, cards))
    entry["spruce_os"] = release
    entry.pop("boot_logos", None)  # App/BootLogo/Imgs/ was replaced
    installed = entry.get("spruce_themes_installed")
    if isinstance(installed, list):
        left = {theme_key(os.path.basename(p)) for p in kept if os.path.dirname(p) != base}
        entry["spruce_themes_installed"] = sorted(t for t in installed if isinstance(t, str) and theme_key(t) in left)
    cards[name] = entry
    if not store.write_cards(cards):
        return 3
    print(ui.green(f"✅ spruceOS {release} installed on {name}") + ui.dim("  (run a sync to fill in the rest)"))
    return 0

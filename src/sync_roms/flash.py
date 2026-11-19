"""Knulli OS images in storage's os/ folder, and which of them fit a device."""
import collections
import gzip
import hashlib
import math
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import zlib
from xml.parsers.expat import ExpatError

from botocore.exceptions import BotoCoreError, ClientError

from . import inventory, picker, runtime, s3, store, ui, usersettings

PREFIX = "os/"
DD = ["sudo", "dd"]
WRITE_BLOCK = 4 * 1024 * 1024
READ_BLOCK = 16 * 1024 * 1024
SPARE = 64 * 1024 * 1024  # free space kept in the temp folder beyond the download


class FlashError(Exception):
    pass


def raw(disk):
    """The raw device node of a disk, which is much faster to write than /dev/diskN."""
    return f"/dev/r{disk}"


def knulli_devices(devices):
    """The devices that run Knulli, in input order."""
    return [d for d in devices if "knulli" in d.get("firmwares", [])]


def images(listing):
    """The keys of the knulli-*.img.gz images directly in os/."""
    return [k for k in listing if re.fullmatch(re.escape(PREFIX) + r"knulli-[^/]*\.img\.gz", k)]


def _date(key):
    found = re.findall(r"(?<!\d)\d{8}(?!\d)", key)
    return found[-1] if found else ""


def _model(key):
    """The device part of an image name, dashes removed: between the chip and -<codename>-<date>."""
    m = re.fullmatch(r"os/knulli-[^-]+-(.+)-[^-]+-\d{8}\.img\.gz", key)
    return m.group(1).replace("-", "") if m else ""


def _matches(key, device_id):
    model = _model(key)
    if not model:
        return False
    return model in (device_id.split("-", 1)[-1].replace("-", ""), device_id.replace("-", ""))


def sort_images(keys, device_id):
    """(key, matches) pairs: matches first, newest date first within each group, then by name."""
    pairs = [(k, _matches(k, device_id)) for k in keys]
    return sorted(pairs, key=lambda p: (not p[1], _neg(_date(p[0])), p[0]))


def _neg(date):
    return -int(date) if date else 0


Disk = collections.namedtuple("Disk", "id size name volumes", defaults=((),))


def _volumes(listing):
    """{whole disk id: its volume names} from a `diskutil list -plist` listing (partitions and APFS volumes)."""
    found = {}
    for entry in listing.get("AllDisksAndPartitions", []):
        names = [v.get("VolumeName") for part in [entry, *entry.get("Partitions", [])]
                 for v in [part, *part.get("APFSVolumes", [])]]
        found[entry.get("DeviceIdentifier")] = tuple(n for n in names if n)
    return found


def parse_disks(listing, info, exclude):
    """The whole disks of a `diskutil list -plist` listing, minus exclude, with size and name read through info(id) and
    volume names from the listing."""
    volumes = _volumes(listing)
    disks = []
    for disk in listing.get("WholeDisks", []):
        if disk in exclude:
            continue
        i = info(disk)
        disks.append(Disk(disk, i.get("TotalSize", i.get("Size")), i.get("MediaName") or i.get("IORegistryEntryName") or "",
                          volumes.get(disk, ())))
    return disks


def _diskutil(*args):
    r = subprocess.run(["diskutil", *args], capture_output=True)
    if r.returncode != 0:
        return None
    try:
        return plistlib.loads(r.stdout)
    except (plistlib.InvalidFileException, ExpatError, ValueError):
        return None


def whole_disks(info):
    """The whole disks behind a `diskutil info -plist` volume: its parent disk and, for APFS, the physical disks under the container."""
    disks = {info["ParentWholeDisk"]} if info.get("ParentWholeDisk") else set()
    for store in info.get("APFSPhysicalStores", []):
        m = re.fullmatch(r"(disk\d+)(?:s\d+)?", store.get("APFSPhysicalStore", ""))
        if m:
            disks.add(m.group(1))
    return disks


def disks_of(path):
    """The whole disks holding path (an APFS volume's container and its physical disk), or an empty set. Unlike clean.card_disk this also answers for the boot disk."""
    mount = os.path.realpath(path)
    while not os.path.ismount(mount):
        mount = os.path.dirname(mount)
    return whole_disks(_diskutil("info", "-plist", mount) or {})


def external_disks(exclude):
    """The external physical disks, minus exclude; [] when diskutil fails."""
    listing = _diskutil("list", "-plist", "external", "physical")
    if listing is None:
        return []
    return parse_disks(listing, lambda d: _diskutil("info", "-plist", d) or {}, exclude)


def _stop(proc):
    """Kill the dd child and reap it."""
    for stream in (proc.stdin, proc.stdout):
        try:
            if stream:
                stream.close()
        except OSError:
            pass
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    if proc.stderr:
        proc.stderr.close()


def write_image(gz_path, disk, progress=None):
    """Stream a .img.gz to the disk through dd. Returns (bytes written, sha256 hexdigest)."""
    proc = None
    try:
        proc = subprocess.Popen(DD + [f"of={raw(disk)}", f"bs={WRITE_BLOCK}", "iflag=fullblock"],
                                stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        total = os.path.getsize(gz_path)
        digest = hashlib.sha256()
        size = 0
        with open(gz_path, "rb") as raw_file, gzip.open(raw_file) as src:
            while True:
                chunk = src.read(WRITE_BLOCK)
                if not chunk:
                    break
                try:
                    proc.stdin.write(chunk)
                except BrokenPipeError:
                    raise FlashError(proc.communicate()[1].decode(errors="replace").strip() or "dd stopped")
                digest.update(chunk)
                size += len(chunk)
                if progress:
                    progress(min(raw_file.tell() / total, 1.0) if total else 1.0)
        try:
            proc.stdin.close()
        except BrokenPipeError:
            pass
        err = proc.communicate()[1].decode(errors="replace").strip()
        if proc.returncode != 0:
            raise FlashError(err or f"dd exited with {proc.returncode}")
        if progress:
            progress(1.0)
        return size, digest.hexdigest()
    except (gzip.BadGzipFile, EOFError, zlib.error) as e:
        _stop(proc)
        raise FlashError(f"the image file is damaged: {e}") from e
    except OSError as e:
        if proc:
            _stop(proc)
        if isinstance(e, BrokenPipeError):
            raise
        raise FlashError(str(e)) from e
    except BaseException:
        if proc:
            _stop(proc)
        raise


def verify(disk, size, digest, progress=None):
    """Read size bytes back from the disk; True when their sha256 equals digest."""
    count = math.ceil(size / READ_BLOCK)
    proc = None
    try:
        proc = subprocess.Popen(DD + [f"if={raw(disk)}", f"bs={READ_BLOCK}", f"count={count}"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        h = hashlib.sha256()
        got = 0
        while got < size:
            chunk = proc.stdout.read(min(WRITE_BLOCK, size - got))
            if not chunk:
                break
            h.update(chunk)
            got += len(chunk)
            if progress:
                progress(got / size)
        proc.stdout.close()
        if got < size:  # stdout hit EOF, so dd is done: its stderr can be read without blocking
            err = proc.stderr.read().decode(errors="replace").strip()
            if proc.wait() != 0:
                raise FlashError(err or f"dd exited with {proc.returncode}")
        _stop(proc)
        return got == size and h.hexdigest() == digest
    except OSError as e:
        if proc:
            _stop(proc)
        raise FlashError(str(e)) from e
    except BaseException:
        if proc:
            _stop(proc)
        raise


def _run(cmd, capture=True):
    """Every command flash runs; capture=False leaves the terminal to it (sudo -v asks for a password there)."""
    return subprocess.run(cmd, capture_output=capture, text=True)


def _sudo():
    """Ask for (or refresh) sudo on the terminal; False when it was refused or cancelled."""
    if _run(["sudo", "-v"], capture=False).returncode != 0:
        ui.failure(ui.red("❌ sudo was refused or cancelled"))
        return False
    return True


def _progress(label):
    """A progress(fraction) callback redrawing one line on a terminal (nothing elsewhere), and a done() ending it."""
    shown = sys.stdout.isatty()

    def draw(fraction):
        if shown:
            sys.stdout.write(f"\r\033[K  {label} {fraction:4.0%}")
            sys.stdout.flush()

    def done():
        if shown:
            sys.stdout.write("\n")
    return draw, done


def _disk_label(disk):
    label = f"{disk.id}  {'?' if disk.size is None else ui.human_size(disk.size)}  {disk.name}"
    return f"{label}  ({', '.join(disk.volumes)})" if disk.volumes else label


def _same(a, b):
    return (a.id, a.size, a.name) == (b.id, b.size, b.name)


def run(args):
    """Pick a Knulli device, image and SD card, write the image to the card and read it back. 0 on success, dry-run or
    Esc; 1 on any failure."""
    if sys.platform != "darwin":
        ui.failure(ui.red("❌ flash needs macOS"))
        return 1
    usersettings.ensure_bucket()
    devices = knulli_devices(store.repo_json("devices"))
    i = picker.filter_list("🎯 Which device?", [d["name"] for d in devices],
                           hint="/ filter · j/k move · Enter continue · Esc quit")
    if i is None:
        return 0
    device = devices[i]
    listing = inventory.files(PREFIX)
    found = sort_images(images(listing), device["id"])
    if not found:
        ui.failure(ui.red("❌ no Knulli images in storage's os/"))
        return 1
    i = picker.filter_list(f"💾 Which image for {device['name']}?", [k[len(PREFIX):] for k, _ in found],
                           extras=[[(f"  {ui.human_size(listing[k])}", "dim"), ("  ✓ matches" if m else "", "green")]
                                   for k, m in found],
                           hint="/ filter · j/k move · Enter continue · Esc quit")
    if i is None:
        return 0
    key = found[i][0]
    gz_size = listing[key]
    tmp = tempfile.mkdtemp(prefix="sync-roms-flash-")
    disk, touched, verified, ejected = None, False, False, False
    try:
        exclude = set()
        for path in ("/", tmp):  # both sit on a local disk, so finding none means diskutil failed
            found = disks_of(path)
            if not found:
                ui.failure(ui.red(f"❌ couldn't tell which disk holds {path}: not flashing"))
                return 1
            exclude |= found
        if runtime.ROOT:
            exclude |= disks_of(runtime.ROOT)
        cards = external_disks(exclude)
        if not cards:
            ui.failure(ui.red("❌ no SD card found"))
            return 1
        i = picker.filter_list("🃏 Which SD card?", [_disk_label(d) for d in cards],
                               hint="/ filter · j/k move · Enter continue · Esc quit")
        if i is None:
            return 0
        disk = cards[i]
        size = "?" if disk.size is None else ui.human_size(disk.size)
        volumes = f": {', '.join(disk.volumes)}" if disk.volumes else ""
        print(ui.yellow(f"⚠️  Everything on {disk.id} ({size}, {disk.name}{volumes}) will be erased."))
        if ui.ask(f"Type {disk.id} to flash it: ").strip() != disk.id:
            ui.failure(ui.red("❌ Not flashed"))
            return 1
        if args.dry_run:
            print(f"Would download {key} ({ui.human_size(gz_size)}) and write it to {disk.id}")
            return 0
        if shutil.disk_usage(tmp).free < gz_size + SPARE:
            ui.failure(ui.red(f"❌ not enough free space in {tempfile.gettempdir()} for {ui.human_size(gz_size)}"))
            return 1
        if not _sudo():
            return 1
        gz_path = os.path.join(tmp, os.path.basename(key))
        draw, done = _progress("⬇️  downloading")
        got = [0]
        lock = threading.Lock()

        def arrived(n):  # boto calls this from several threads
            with lock:
                got[0] += n
                draw(min(got[0] / gz_size, 1.0) if gz_size else 1.0)
        try:
            s3.download((key, gz_path, gz_size), arrived)
        except (OSError, BotoCoreError, ClientError) as e:
            done()
            ui.failure(ui.red(f"❌ download failed: {e}"))
            return 1
        done()
        if not _sudo():
            return 1
        if not any(_same(disk, d) for d in external_disks(exclude)):  # disk numbers are reused: a card swapped since the pick could be another drive
            ui.failure(ui.red(f"❌ {disk.id} changed since you picked it: not flashed"))
            return 1
        touched = True
        r = _run(["diskutil", "unmountDisk", disk.id])
        if r.returncode != 0:
            ui.failure(ui.red(f"❌ couldn't unmount {disk.id}: {(r.stderr or r.stdout).strip()}"))
            return 1
        draw, done = _progress(f"✍️  writing {disk.id}")
        try:
            written, digest = write_image(gz_path, disk.id, draw)
        except FlashError as e:
            done()
            ui.failure(ui.red(f"❌ flash failed: {e}"))
            return 1
        done()
        _run(["sync"])
        _run(["diskutil", "unmountDisk", disk.id])
        if not _sudo():
            return 1
        draw, done = _progress(f"🔍 verifying {disk.id}")
        try:
            verified = verify(disk.id, written, digest, draw)
        except FlashError as e:
            done()
            ui.failure(ui.red(f"❌ verify failed: {e}"))
            return 1
        done()
        if not verified:
            ui.failure(ui.red("❌ flash failed: the card doesn't match the image: try again or use another card"))
            return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if touched:
            _run(["sync"])
            ejected = _run(["diskutil", "eject" if verified else "unmountDisk", disk.id]).returncode == 0 and verified
    if not ejected:
        ui.warn(f"Flashed and verified, but {disk.id} didn't eject: eject it before removing the card")
        return 0
    print(ui.green("✅ Flashed and verified — safe to remove the card"))
    return 0

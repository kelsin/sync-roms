"""Knulli OS images in storage's os/ folder, and which of them fit a device."""
import collections
import gzip
import hashlib
import math
import os
import plistlib
import re
import subprocess
import zlib
from xml.parsers.expat import ExpatError

PREFIX = "os/"
DD = ["sudo", "dd"]
WRITE_BLOCK = 4 * 1024 * 1024
READ_BLOCK = 16 * 1024 * 1024


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


Disk = collections.namedtuple("Disk", "id size name")


def parse_disks(listing, info, exclude):
    """The whole disks of a `diskutil list -plist` listing, minus exclude, with size and name read through info(id)."""
    disks = []
    for disk in listing.get("WholeDisks", []):
        if disk in exclude:
            continue
        i = info(disk)
        disks.append(Disk(disk, i.get("TotalSize", i.get("Size")), i.get("MediaName") or i.get("IORegistryEntryName") or ""))
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
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
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

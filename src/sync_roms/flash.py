"""Knulli OS images in storage's os/ folder, and which of them fit a device."""
import collections
import os
import plistlib
import re
import subprocess
from xml.parsers.expat import ExpatError

PREFIX = "os/"


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

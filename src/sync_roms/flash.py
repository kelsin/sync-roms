"""Knulli OS images in storage's os/ folder, and which of them fit a device."""
import re

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

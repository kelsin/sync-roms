"""Android bezels in storage: os/android/bezels/<device id>/..., copied to an esde card's Bezels/ folder."""
import os

from . import downloads, inventory

PREFIX = "os/android/bezels/"


def _listing():
    return {k: v for k, v in inventory.files(PREFIX).items()
            if not k.endswith("/") and os.path.basename(k) != ".DS_Store"}


def files(device_id):
    """{storage key: size} of the files under the device's folder."""
    if not device_id:
        return {}
    folder = PREFIX + device_id + "/"
    return {k: v for k, v in _listing().items() if k.startswith(folder)}


def devices():
    """Sorted ids of the devices with at least one bezel file."""
    return sorted({k[len(PREFIX):].split("/", 1)[0] for k in _listing() if "/" in k[len(PREFIX):]})


def jobs(device_id, card_base):
    """Download jobs (key, path, size) of the device's files into card_base/Bezels/."""
    out = []
    for k, size in sorted(files(device_id).items()):
        downloads.add_job(out, k, os.path.join(card_base, "Bezels"), k[len(PREFIX + device_id + "/"):], size)
    return out

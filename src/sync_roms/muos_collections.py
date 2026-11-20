"""muOS collections: where each storage choice is mounted on the device."""

MOUNTS = {"sd1": "/mnt/mmc", "sd2": "/mnt/sdcard"}


def mount(entry):
    """The mount of a card's muOS storage (default sd1), or None when the value is unknown."""
    return MOUNTS.get(entry.get("muos_storage", "sd1"))

"""The Syncthing settings sync puts on spruce cards (data/syncthing.json), switched off by `spruce_syncthing: false`."""
from . import store, usersettings

NO_WIFI_SKIPS = ("Network Settings", "enableSyncthing")


def data():
    return store.repo_json("syncthing")


def enabled():
    return usersettings.load_settings().get("spruce_syncthing") is not False


def forced_keys():
    """Every (section, key) the Syncthing data sets on a spruce card."""
    return {(section, key) for section, keys in data()["spruce"]["settings"].items() for key in keys}


def forced_settings(card):
    """[(section, key, value)] sync sets on the card's spruce-config.json: [] when off, and without enableSyncthing on a device with no WiFi."""
    if not enabled():
        return []
    device = store.saved_card(card).get("device")
    no_wifi = any(d.get("id") == device and d.get("network") is False for d in store.repo_json("devices"))
    return [(section, key, value) for section, keys in data()["spruce"]["settings"].items()
            for key, value in keys.items() if not (no_wifi and (section, key) == NO_WIFI_SKIPS)]

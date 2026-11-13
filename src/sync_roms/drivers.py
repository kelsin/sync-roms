"""Custom Adreno GPU driver zips from GitHub releases, kept in storage and copied to Android cards."""
import re

from . import store

PREFIX = "os/drivers/"


class NoAsset(Exception):
    pass


def load():
    return store.repo_json("drivers")


def for_device(device, layout_name):
    """The driver entries for the device's GPU, in list order; only Android (ES-DE) cards use them."""
    gpu = (device or {}).get("gpu")
    if layout_name != "esde" or not gpu:
        return []
    data = load()
    by_id = {d["id"]: d for d in data["drivers"]}
    return [by_id[i] for i in data["gpus"].get(gpu, {}).get("drivers", [])]


def pick_release(driver, releases):
    """(tag, asset) of the release to use. A driver with a tag takes that release; otherwise the newest (the order given)
    non-draft release with a matching asset, preferring full releases over prereleases."""
    repo, pattern = driver["repo"], re.compile(driver["asset"])
    if driver.get("tag"):
        candidates = [r for r in releases if r["tag_name"] == driver["tag"]]
    else:
        candidates = [r for r in releases if not r.get("draft")]
        candidates = [r for r in candidates if not r.get("prerelease")] + [r for r in candidates if r.get("prerelease")]
    for release in candidates:
        matches = [a for a in release.get("assets", []) if pattern.search(a["name"])]
        if len(matches) > 1:
            names = ", ".join(a["name"] for a in matches)
            raise NoAsset(f"{len(matches)} assets of {repo} {release['tag_name']} match {driver['asset']}: {names}")
        if matches:
            return release["tag_name"], matches[0]
    where = f"release {driver['tag']} of {repo}" if driver.get("tag") else f"release of {repo}"
    raise NoAsset(f"no {where} has an asset matching {driver['asset']}")


def card_name(driver_id, tag):
    return f"{driver_id}-{re.sub(r'[^A-Za-z0-9._-]', '_', tag)}.zip"

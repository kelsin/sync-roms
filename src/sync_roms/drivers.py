"""Custom Adreno GPU driver zips from GitHub releases, kept in storage and copied to Android cards."""
import http.client
import os
import re
import shutil
import tempfile
import zipfile

from . import github, inventory, runtime, s3, store, ui

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


def can_write():
    """Whether storage can be written: a storage folder always, a bucket when the write profile exists."""
    if runtime.ROOT:
        return True
    import boto3
    from botocore.exceptions import ProfileNotFound
    try:
        boto3.Session(profile_name=runtime.WRITE_PROFILE)
    except ProfileNotFound:
        return False
    return True


def stored_tag(driver_id):
    """The release tag of the driver's zip in storage (never the mirror), or None when there is no .tag."""
    from . import mirroring
    try:
        with mirroring.storage_reads():
            return s3.get_text(f"{PREFIX}{driver_id}.tag").strip()
    except s3.ERRORS as e:
        if s3.missing(e):
            return None
        raise


def _latest(driver):
    repo = driver["repo"]
    if driver.get("tag"):
        releases = [github.json(f"https://api.github.com/repos/{repo}/releases/tags/{driver['tag']}")]
    else:
        releases = github.json(f"https://api.github.com/repos/{repo}/releases?per_page=100")
    return pick_release(driver, releases)


def _update(driver, stored, dry_run):
    key = f"{PREFIX}{driver['id']}"
    if driver.get("tag") and f"{key}.zip" in stored:
        return
    tag, asset = _latest(driver)
    old = stored_tag(driver["id"])
    if old == tag:
        return
    if dry_run:
        print(ui.dim(f"🧪 Dry run: would store {driver['name']} {tag}"))
        return
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "driver.zip")
        with github.get(asset["browser_download_url"]) as r, open(path, "wb") as f:
            shutil.copyfileobj(r, f)
        if not zipfile.is_zipfile(path):
            raise OSError(f"{asset['name']} isn't a zip file")
        s3.put_file(f"{key}.zip", path)  # the zip first, so a .tag never names a zip that isn't there
        s3.put_text(f"{key}.tag", tag + "\n")
        if runtime._mirror_root:
            for suffix, source in ((".zip", path), (".tag", None)):
                target = s3.safe_join(runtime._mirror_root, key + suffix)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if source:
                    shutil.copyfile(source, target)
                else:
                    with open(target, "w", encoding="utf-8") as f:
                        f.write(tag + "\n")
    print(f"🎮 {driver['name']}: {old or 'none in storage'} → {tag}")


def refresh(entries, dry_run):
    """Keep the newest release zip of each driver (a pinned one once) in storage. A failure warns and moves on."""
    stored = inventory.files(PREFIX, sizes=False)
    for driver in entries:
        try:
            _update(driver, stored, dry_run)
        except (OSError, http.client.HTTPException, NoAsset, ValueError, KeyError, TypeError, *s3.ERRORS) as e:
            ui.warn(f"Couldn't update the {driver['name']} driver: {e}")


def jobs(entries, drivers_dir):
    """(storage key, card path, size) of each driver whose zip (with its .tag) is in storage, named by id and tag; the
    others are reported missing."""
    stored = inventory.files(PREFIX)
    out, missing = [], []
    for driver in entries:
        key = f"{PREFIX}{driver['id']}.zip"
        tag = stored_tag(driver["id"]) if key in stored else None
        if tag:
            out.append((key, os.path.join(drivers_dir, card_name(driver["id"], tag)), stored[key]))
        else:
            missing.append(key)
    ui.report_missing(missing, "driver(s)")
    return out


def prune(card, drivers_dir, current, dry_run):
    """Remove the files in drivers_dir that the card's saved drivers list names but current doesn't (never another
    file), then save current as the list. The names removed (or, in a dry run, that would be)."""
    entry = store.load_cards().get(card)
    entry = entry if isinstance(entry, dict) else {}
    saved = entry.get("drivers")
    saved = [n for n in saved if isinstance(n, str)] if isinstance(saved, list) else []
    removed = [n for n in saved if n not in current and os.path.isfile(os.path.join(drivers_dir, os.path.basename(n)))]
    if dry_run:
        return removed
    for name in removed:
        os.remove(os.path.join(drivers_dir, os.path.basename(name)))
    if entry.get("drivers") != sorted(current):
        store.update_card(card, drivers=sorted(current))
    return removed

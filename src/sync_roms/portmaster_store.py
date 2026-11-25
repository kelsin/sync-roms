"""PortMaster ports and runtimes in storage: `ports download` puts them there, with each port's facts in
scrapes/ports/metadata.json so a sync never opens a zip."""
import hashlib
import http.client
import os
import tempfile

from . import drivers, github, inventory, portmaster_catalog, runtime, s3, scrape_plan, shared, ui, usersettings

PORTS = "ports/"
RUNTIMES = "os/portmaster/runtimes/"
META = scrape_plan.metadata_key("ports")
_HTTP_ERRORS = (OSError, http.client.HTTPException)


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _title(zip_, entry):
    return (entry.get("attr") or {}).get("title") or zip_


def _facts(entry):
    """The port facts sync needs, as kept under "portmaster" in the metadata."""
    attr, source = entry.get("attr") or {}, entry.get("source") or {}
    items = list(entry.get("items") or [])
    folder = next((i.rstrip("/") for i in items if not i.endswith(".sh")), None)
    return {"folder": folder, "items": items, "rtr": bool(attr.get("rtr")), "inst": attr.get("inst") or "",
            "runtime": portmaster_catalog.runtimes(entry), "md5": source.get("md5"), "size": source.get("size")}


def outdated(catalog):
    """The catalogue's zips in storage whose metadata md5 (none counts) differs from the catalogue's source md5."""
    stored = set(inventory.files(PORTS, sizes=False))
    meta = scrape_plan.load_metadata("ports")
    return sorted(zip_ for zip_, entry in portmaster_catalog.ports(catalog).items() if PORTS + zip_ in stored
                  and ((meta.get(zip_) or {}).get("portmaster") or {}).get("md5") != (entry.get("source") or {}).get("md5"))


def remind_outdated(catalog):
    try:
        old = outdated(catalog)
    except (*s3.ERRORS, ValueError):
        return
    if old:
        ports = portmaster_catalog.ports(catalog)
        titles = ", ".join(_title(z, ports[z]) for z in old)
        print(ui.yellow(f"{len(old)} ports in storage have newer versions: {titles}. Run sync-roms ports download --update"))


def _fetch(url, md5, path):
    """Download url to path and check its md5. The problem as text, or None."""
    try:
        github.download(url, path)
    except _HTTP_ERRORS as e:
        return f"couldn't download {url} ({e})"
    if _md5(path) != md5:
        return f"the md5 of {url} isn't the catalogue's"
    return None


def _put(key, url, md5, tmp):
    """Download to tmp, check and upload to key. True when it is in storage."""
    path = os.path.join(tmp, os.path.basename(key))
    problem = _fetch(url, md5, path)
    if problem is None:
        try:
            s3.put_file(key, path)
        except s3.ERRORS as e:
            problem = f"couldn't write {key} to {s3.location()} ({e})"
    if os.path.exists(path):
        os.remove(path)
    if problem:
        ui.warn(problem)
        return False
    print(ui.green(f"  ✅ {key}"))
    return True


def _record(zip_, entry):
    def change(data):
        fields = data.setdefault(zip_, {})
        fields.setdefault("name", _title(zip_, entry))
        fields["portmaster"] = _facts(entry)
    shared.update(META, lambda text: scrape_plan.parse_metadata(text, META), {}, change, scrape_plan.dump_json)


def download(names, update=False, refresh=False, dry_run=False):
    """Put the named ports (all outdated ones for update with no names) and their runtimes in storage. Exit code."""
    usersettings.ensure_bucket()
    if runtime.ROOT and not os.path.isdir(runtime.ROOT):
        ui.warn(f"The storage folder {runtime.ROOT} isn't there (is it mounted?)")
        return 3
    if not dry_run and not drivers.can_write():
        ui.fail(f"No write access to {s3.location()}: `ports download` adds files to storage")
    catalog = portmaster_catalog.load(refresh=refresh)
    if catalog is None:
        return 1
    failed = False
    try:
        if update and not names:
            names = outdated(catalog)
            if not names:
                print(ui.green("✅ every port in storage is up to date"))
        stored = set(inventory.files(PORTS, sizes=False))
        runtimes = set(inventory.files(RUNTIMES, sizes=False))
        meta = scrape_plan.load_metadata("ports", fresh=True)
    except (*s3.ERRORS, ValueError) as e:
        ui.warn(f"Couldn't read storage ({e})")
        return 1
    ports = portmaster_catalog.ports(catalog)
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            zip_ = portmaster_catalog.resolve(catalog, name)
            if zip_ is None:
                ui.warn(f"{name} isn't an aarch64 port in PortMaster's catalogue")
                failed = True
                continue
            entry, key = ports[zip_], PORTS + zip_
            source = entry.get("source") or {}
            if key in stored and (not update or ((meta.get(zip_) or {}).get("portmaster") or {}).get("md5") == source.get("md5")):
                print(ui.dim(f"  {key}: in storage"))
                continue
            needed = [r for r in portmaster_catalog.runtimes(entry) if RUNTIMES + r not in runtimes]
            if dry_run:
                print(f"  would download {key}" + "".join(f", {RUNTIMES}{r}" for r in needed))
                continue
            print(ui.bold(f"⬇️  {_title(zip_, entry)} ({zip_})"))
            if not _put(key, source.get("url"), source.get("md5"), tmp):
                failed = True
                continue
            for rt in needed:
                src = portmaster_catalog.runtime_source(catalog, rt)
                if src is None:
                    ui.warn(f"{rt}, a runtime of {zip_}, isn't in PortMaster's catalogue")
                    failed = True
                elif _put(RUNTIMES + rt, src.get("url"), src.get("md5"), tmp):
                    runtimes.add(RUNTIMES + rt)
                else:
                    failed = True
            try:
                _record(zip_, entry)
            except (*s3.ERRORS, ValueError) as e:
                ui.warn(f"Couldn't write {META} ({e})")
                failed = True
    if dry_run:
        print(ui.dim("🧪 Dry run: nothing downloaded or written"))
    if not update:
        remind_outdated(catalog)
    return 1 if failed else 0

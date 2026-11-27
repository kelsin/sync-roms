"""`config push USER@HOST`: copy settings.json (without the storage and Mac-only settings) and every collection to a SteamOS device
over SSH. The device keeps its own values of NEVER_SENT; its collections are made to match this machine's exactly."""
import io
import json
import os
import shlex
import subprocess
import tarfile

from . import collections, ui, usersettings

NEVER_SENT = ("bucket", "root", "endpoint", "profile", "write_profile", "mirror", "eject", "storage_cache_declined")
SSH = ("ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10")


def _ssh(host, script, data=None):
    """stdout of script run on host by its login shell; raises CalledProcessError or OSError."""
    return subprocess.run([*SSH, "--", host, script], input=data, capture_output=True, check=True).stdout


def merge(mac, device):
    """The settings the device gets: mac's without NEVER_SENT, plus the device's own NEVER_SENT values."""
    merged = {k: v for k, v in mac.items() if k not in NEVER_SENT}
    merged.update({k: v for k, v in (device or {}).items() if k in NEVER_SENT})
    return merged


def changes(old, new):
    """Sorted "added|changed|removed <key>" lines from old to new; never their values."""
    old = old or {}
    return sorted([f"added {k}" for k in new.keys() - old.keys()] + [f"removed {k}" for k in old.keys() - new.keys()]
                  + [f"changed {k}" for k in new.keys() & old.keys() if new[k] != old[k]])


def remote_dir(host):
    """The device's data folder, as store.data_dir() finds it on Linux."""
    script = 'if [ -n "$XDG_DATA_HOME" ]; then printf %s/sync-roms "$XDG_DATA_HOME"; else printf %s/.sync-roms "$HOME"; fi'
    return _ssh(host, script).decode()


def fetch(host, data_dir):
    """(settings.json's bytes or None, {collection file name: bytes}) in the device's data_dir."""
    script = (f"cd {shlex.quote(data_dir)} 2>/dev/null || {{ tar -cf - -T /dev/null; exit; }}; set --; "
              '[ -f settings.json ] && set -- settings.json; for f in collections/*.json; do [ -f "$f" ] && set -- "$@" "$f"; done; '
              'if [ $# -eq 0 ]; then tar -cf - -T /dev/null; else tar -cf - "$@"; fi')
    settings, found = None, {}
    with tarfile.open(fileobj=io.BytesIO(_ssh(host, script)), mode="r:") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            if member.name == "settings.json":
                settings = tar.extractfile(member).read()
            elif member.name.startswith("collections/") and member.name.count("/") == 1:
                found[member.name.split("/", 1)[1]] = tar.extractfile(member).read()
    return settings, found


def send(host, data_dir, settings, collections):
    """Replace the device's settings.json (mode 600) and collections/ folder with these, through a temp folder in data_dir."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in [("settings.json", settings)] + [(f"collections/{n}", d) for n, d in sorted(collections.items())]:
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o600
            tar.addfile(info, io.BytesIO(data))
    folder = shlex.quote(data_dir)
    script = (f"set -e; mkdir -p {folder}; cd {folder}; tmp=$(mktemp -d .push.XXXXXX); trap 'rm -rf \"$tmp\"' EXIT; "
              'tar -xf - -C "$tmp"; chmod 600 "$tmp/settings.json"; mv -f "$tmp/settings.json" settings.json; '
              'mkdir -p "$tmp/collections"; if [ -d collections ]; then mv collections "$tmp/old"; fi; mv "$tmp/collections" collections')
    _ssh(host, script, buf.getvalue())


def _mac_collections():
    folder = collections.collections_dir()
    found = {}
    for entry in os.scandir(folder) if os.path.isdir(folder) else []:
        if entry.name.endswith(".json") and entry.is_file():
            with open(entry.path, "rb") as f:
                found[entry.name] = f.read()
    return found


def push(host, dry_run):
    mac = usersettings.load_settings()
    mine = _mac_collections()
    try:
        data_dir = remote_dir(host)
        raw, theirs = fetch(host, data_dir)
    except (subprocess.CalledProcessError, OSError, tarfile.TarError) as e:
        detail = (getattr(e, "stderr", None) or b"").decode(errors="replace").strip() or str(e)
        ui.fail(f"Can't reach {host} over SSH: {detail}", 1)
    device = None
    if raw is not None:
        try:
            device = json.loads(raw)
        except ValueError:
            device = None
        if not isinstance(device, dict):
            ui.fail(f"{host}:{data_dir}/settings.json isn't a valid JSON object: fix or move it", 3)
    settings = merge(mac, device)
    lines = changes(device, settings) + sorted(
        [f"added collection {n[:-5]}" for n in mine.keys() - theirs.keys()]
        + [f"removed collection {n[:-5]}" for n in theirs.keys() - mine.keys()]
        + [f"changed collection {n[:-5]}" for n in mine.keys() & theirs.keys() if mine[n] != theirs[n]])
    print(ui.bold(f"⚙️  {host}") + ui.dim(f"  {data_dir}"))
    if not lines:
        print(ui.dim("Nothing to change"))
        return 0
    for line in lines:
        print(f"  {line}")
    if dry_run:
        return 0
    try:
        send(host, data_dir, (json.dumps(settings, indent=2, sort_keys=True) + "\n").encode(), mine)
    except (subprocess.CalledProcessError, OSError) as e:
        detail = (getattr(e, "stderr", None) or b"").decode(errors="replace").strip() or str(e)
        ui.fail(f"Can't reach {host} over SSH: {detail}", 1)
    print(ui.green(f"✅ Pushed settings and collections to {host}"))
    return 0

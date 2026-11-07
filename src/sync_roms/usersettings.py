"""User settings file and bucket selection."""
import json
import os
import re
import stat
import sys

from . import runtime, store, ui


# --- Local mirror ---------------------------------------------------------------------------------

def _private(path):
    """Make settings.json readable by the owner only (it can hold the ScreenScraper credentials)."""
    if sys.platform == "win32":
        return
    try:
        if stat.S_IMODE(os.stat(path).st_mode) != 0o600:
            os.chmod(path, 0o600)
    except OSError:
        pass


def load_settings():
    """Saved global settings: {"bucket": S3 bucket name, "root": folder used instead of a bucket, "endpoint": custom S3 endpoint URL, "profile"/"write_profile": aws profiles, "mirror": folder of the local mirror, "screenscraper_user"/"screenscraper_password"/"screenscraper_devid"/"screenscraper_devpassword": ScreenScraper credentials (never shown by config show)}."""
    path = os.path.join(store.data_dir(), "settings.json")
    try:
        with open(path) as f:
            settings = json.load(f)
    except (OSError, ValueError):
        return {}
    _private(path)
    return settings if isinstance(settings, dict) else {}


def save_setting(name, value):
    """Set a global setting, or remove it when value is None."""
    settings = load_settings()
    if value is None:
        settings.pop(name, None)
    else:
        settings[name] = value
    try:
        os.makedirs(store.data_dir(), exist_ok=True)
        path = os.path.join(store.data_dir(), "settings.json")
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            if sys.platform != "win32":  # an existing file keeps its mode through os.open: tighten it before writing
                os.fchmod(f.fileno(), 0o600)
            json.dump(settings, f, indent=2, sort_keys=True)
        _private(path)
    except OSError as e:
        ui.fail(f"Couldn't save the setting: {e}", 3)


SETTINGS = (("bucket", "ROMS_BUCKET", None), ("root", "ROMS_ROOT", None), ("endpoint", "ROMS_ENDPOINT", None),
            ("profile", "ROMS_PROFILE", "roms-readonly"), ("write_profile", "ROMS_WRITE_PROFILE", "roms"))


def resolve_settings():
    """{name: (value, source)} for bucket, root, endpoint, profile and write_profile: flag, then environment, then settings.json, then default."""
    saved = load_settings()
    out = {}
    for name, env, default in SETTINGS:
        if runtime.OVERRIDES.get(name):
            out[name] = (runtime.OVERRIDES[name], "--" + name.replace("_", "-"))
        elif os.environ.get(env):
            out[name] = (os.environ[env], f"env {env}")
        elif saved.get(name):
            out[name] = (saved[name], "settings.json")
        else:
            out[name] = (default, "default" if default else "unset")
    return out


def apply_settings():
    """Set runtime.BUCKET, ROOT, ENDPOINT, PROFILE and WRITE_PROFILE from resolve_settings(); never prompts."""
    resolved = {name: value for name, (value, _) in resolve_settings().items()}
    runtime.PROFILE, runtime.WRITE_PROFILE = resolved["profile"], resolved["write_profile"]
    runtime.BUCKET, runtime.ENDPOINT = resolved["bucket"], resolved["endpoint"] or None
    runtime.ROOT = os.path.abspath(os.path.expanduser(resolved["root"])) if resolved["root"] else None  # a root wins over a bucket


def ensure_bucket():
    """Apply the settings, asking for the bucket (and an optional endpoint) or a storage folder on first run."""
    apply_settings()
    while not (runtime.BUCKET or runtime.ROOT):
        try:
            name = input("🪣 Which S3 bucket holds your ROMs? (or a folder path, e.g. /Volumes/roms) ").strip()
        except EOFError:
            ui.fail("No bucket given", 3)
        if name.startswith(("/", "~", ".")):  # a bucket name can't start with these
            root = os.path.abspath(os.path.expanduser(name))
            if not os.path.isdir(root):
                print(ui.red(f"❌ {root} is not a folder"))
                continue
            save_setting("root", root)
            save_setting("bucket", None)
            save_setting("endpoint", None)
            runtime.ROOT = root
            continue
        name = re.sub(r"^s3://", "", name).strip("/")
        if name:
            save_setting("bucket", name)
            runtime.BUCKET = name
            try:
                url = input("🔗 Custom S3 endpoint URL (blank for AWS): ").strip()
            except EOFError:
                url = ""
            if url:
                save_setting("endpoint", url)
                runtime.ENDPOINT = url

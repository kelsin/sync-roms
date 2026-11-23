"""User settings file and bucket selection."""
import json
import os
import re
import stat
import sys

from . import runtime, store, ui


def _private(path):
    """Make settings.json readable by the owner only (it can hold the ScreenScraper credentials)."""
    if sys.platform == "win32":
        return
    try:
        if stat.S_IMODE(os.stat(path).st_mode) != 0o600:
            os.chmod(path, 0o600)
    except OSError:
        pass


def _read():
    """(settings, problem): settings.json's contents ({} when missing), and why it can't be used, or None."""
    path = os.path.join(store.data_dir(), "settings.json")
    try:
        with open(path) as f:
            settings = json.load(f)
    except FileNotFoundError:
        return {}, None
    except OSError as e:
        return {}, f"Can't read {path} ({e.strerror}): fix or move it"
    except ValueError as e:
        where = f" (line {e.lineno}, column {e.colno})" if isinstance(e, json.JSONDecodeError) else ""
        return {}, f"{path} isn't valid JSON{where}: fix or move it"
    if not isinstance(settings, dict):
        return {}, f"{path} isn't a JSON object: fix or move it"
    _private(path)
    return settings, None


def settings_problem():
    """Why settings.json can't be used, or None when it is fine or missing."""
    return _read()[1]


def load_settings():
    """Saved global settings: {"bucket": S3 bucket name, "root": folder used instead of a bucket, "endpoint": custom S3 endpoint URL, "profile"/"write_profile": aws profiles, "mirror": folder of the local mirror, "surprise_ttl_days": days before a surprise may repeat (default 183), "surprise_excluded_systems": system ids Surprise never picks from, "screenscraper_user"/"screenscraper_password": ScreenScraper login (never shown by config show), "spruce_ra_mode"/"spruce_ra_username"/"spruce_ra_password"/"spruce_ra_api_key"/"spruce_ra_offline_proxy"/"spruce_ra_proxy_stats": RetroAchievements settings written to spruce cards, "spruce_settings": {section: {key: value}} of other spruceOS preferences, from `config import`, "wifi_networks": [{"ssid", "psk"?}] WiFi networks written to spruce cards' wpa_supplicant.conf, "spruce_themes": [PyUI theme folder names] every spruce card gets, from `themes pick`}.
    {} when the file is missing; stops (exit 3) when it is there but unreadable, so it is never overwritten."""
    settings, problem = _read()
    if problem:
        ui.fail(problem, 3)
    return settings


def save_settings(settings):
    """Replace settings.json with settings in one atomic write: a mode 600 temp file in the same folder, then a rename.
    The file from before this run is kept as settings.json.bak, also mode 600. Stops when the file can't be parsed."""
    problem = settings_problem()
    if problem:
        ui.fail(problem, 3)
    path = os.path.join(store.data_dir(), "settings.json")
    try:
        os.makedirs(store.data_dir(), exist_ok=True)
        if os.path.exists(path) and sys.platform != "win32":  # the copy keeps the .bak's mode, so make it 600 first
            os.close(os.open(path + ".bak", os.O_WRONLY | os.O_CREAT, 0o600))
            _private(path + ".bak")
        store.write_json(path, settings, backup=True, mode=0o600, indent=2, sort_keys=True)
    except OSError as e:
        ui.fail(f"Couldn't save the setting: {e}", 3)


def save_setting(name, value):
    """Set a global setting, or remove it when value is None."""
    settings = load_settings()
    if value is None:
        settings.pop(name, None)
    else:
        settings[name] = value
    save_settings(settings)


SETTINGS = (("bucket", "ROMS_BUCKET", None), ("root", "ROMS_ROOT", None), ("endpoint", "ROMS_ENDPOINT", None),
            ("profile", "ROMS_PROFILE", "roms-readonly"), ("write_profile", "ROMS_WRITE_PROFILE", "roms"))


def resolve_settings(saved=None):
    """{name: (value, source)} for bucket, root, endpoint, profile and write_profile: flag, then environment, then settings.json, then default.
    saved: settings to use instead of reading settings.json."""
    saved = load_settings() if saved is None else saved
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
    """Set runtime.BUCKET, ROOT, ENDPOINT, PROFILE and WRITE_PROFILE from resolve_settings(); never prompts.
    A settings.json that can't be parsed is skipped here (so `doctor` can report it) and stops load_settings() callers."""
    resolved = {name: value for name, (value, _) in (resolve_settings({}) if settings_problem() else resolve_settings()).items()}
    runtime.PROFILE, runtime.WRITE_PROFILE = resolved["profile"], resolved["write_profile"]
    runtime.BUCKET, runtime.ENDPOINT = resolved["bucket"], resolved["endpoint"] or None
    runtime.ROOT = os.path.abspath(os.path.expanduser(resolved["root"])) if resolved["root"] else None  # a root wins over a bucket


def ensure_bucket():
    """Apply the settings, asking for the bucket (and an optional endpoint) or a storage folder on first run."""
    load_settings()  # stops on a settings.json that can't be parsed before asking anything
    apply_settings()
    while not (runtime.BUCKET or runtime.ROOT):
        try:
            name = ui._input("🪣 Which S3 bucket holds your ROMs? (or a folder path, e.g. /Volumes/roms) ").strip()
        except EOFError:
            ui.fail("No storage given: set ROMS_BUCKET or ROMS_ROOT, or pass --bucket or --root", 3)
        if not name.startswith("s3://") and ("/" in name or name.startswith((".", "~")) or os.path.isdir(name)):  # a bucket name has no "/"
            root = os.path.expanduser(name)
            if not os.path.isabs(root):
                ui.failure(ui.red(f"❌ {name} is not an absolute path: give the whole folder path, e.g. /Volumes/roms"))
                continue
            root = os.path.abspath(root)
            if not os.path.isdir(root):
                ui.failure(ui.red(f"❌ {root} is not a folder"))
                continue
            settings = {k: v for k, v in load_settings().items() if k not in ("bucket", "endpoint")}
            save_settings({**settings, "root": root})
            runtime.ROOT = root
            continue
        name = re.sub(r"^s3://", "", name).strip("/")
        if name:
            save_setting("bucket", name)
            runtime.BUCKET = name
            try:
                url = ui._input("🔗 Custom S3 endpoint URL (blank for AWS): ").strip()
            except EOFError:
                url = ""
            if url:
                save_setting("endpoint", url)
                runtime.ENDPOINT = url

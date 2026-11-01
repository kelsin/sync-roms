"""User settings file and bucket selection."""
import json
import os
import re

from . import runtime, store, ui


# --- Local mirror ---------------------------------------------------------------------------------

def load_settings():
    """Saved global settings: {"bucket": S3 bucket name, "endpoint": custom S3 endpoint URL, "profile"/"write_profile": aws profiles, "mirror": folder of the local mirror}."""
    try:
        with open(os.path.join(store.data_dir(), "settings.json")) as f:
            settings = json.load(f)
    except (OSError, ValueError):
        return {}
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
        with open(os.path.join(store.data_dir(), "settings.json"), "w") as f:
            json.dump(settings, f, indent=2, sort_keys=True)
    except OSError as e:
        ui.fail(f"Couldn't save the setting: {e}", 3)


SETTINGS = (("bucket", "ROMS_BUCKET", None), ("endpoint", "ROMS_ENDPOINT", None),
            ("profile", "ROMS_PROFILE", "roms-readonly"), ("write_profile", "ROMS_WRITE_PROFILE", "roms"))


def resolve_settings():
    """{name: (value, source)} for bucket, endpoint, profile and write_profile: flag, then environment, then settings.json, then default."""
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
    """Set runtime.BUCKET, ENDPOINT, PROFILE and WRITE_PROFILE from resolve_settings(); never prompts."""
    resolved = {name: value for name, (value, _) in resolve_settings().items()}
    runtime.PROFILE, runtime.WRITE_PROFILE = resolved["profile"], resolved["write_profile"]
    runtime.BUCKET, runtime.ENDPOINT = resolved["bucket"], resolved["endpoint"] or None


def ensure_bucket():
    """Apply the settings, asking for the bucket (and an optional endpoint) on first run."""
    apply_settings()
    while not runtime.BUCKET:
        try:
            name = input("🪣 Which S3 bucket holds your ROMs? ").strip()
        except EOFError:
            ui.fail("No bucket given", 3)
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

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


def ensure_bucket():
    """Set BUCKET and ENDPOINT from the saved settings, asking for the bucket (and an optional endpoint) on first run."""
    settings = load_settings()
    runtime.PROFILE = os.environ.get("ROMS_PROFILE") or settings.get("profile") or "roms-readonly"
    runtime.WRITE_PROFILE = os.environ.get("ROMS_WRITE_PROFILE") or settings.get("write_profile") or "roms"
    runtime.BUCKET = os.environ.get("ROMS_BUCKET") or settings.get("bucket")
    runtime.ENDPOINT = os.environ.get("ROMS_ENDPOINT") or settings.get("endpoint") or None
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

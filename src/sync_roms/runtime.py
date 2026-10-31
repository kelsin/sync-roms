"""Process-wide settings read as `config.NAME` so reassignment is seen everywhere."""
import os


BUCKET = None  # set by ensure_bucket() from settings.json
ENDPOINT = None  # custom S3 endpoint URL from settings.json; None means AWS
PROFILE = os.environ.get("ROMS_PROFILE", "roms-readonly")
WRITE_PROFILE = os.environ.get("ROMS_WRITE_PROFILE", "roms")
WORKERS = 8
MAX_MISSING_SHOWN = 5
MIRROR_MARKER = ".sync-roms-mirror"  # only folders holding this file are ever written to or pruned as a mirror
_mirror_root = None  # set once a sync reads from the local mirror instead of the bucket

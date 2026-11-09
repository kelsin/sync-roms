"""Process-wide settings read as `runtime.NAME` so reassignment is seen everywhere."""
import os


BUCKET = None  # set by ensure_bucket() from settings.json
ROOT = None  # folder (e.g. a mounted network share) used instead of the bucket; set from settings.json
ENDPOINT = None  # custom S3 endpoint URL from settings.json; None means AWS
PROFILE = os.environ.get("ROMS_PROFILE", "roms-readonly")
WRITE_PROFILE = os.environ.get("ROMS_WRITE_PROFILE", "roms")
OVERRIDES = {}  # settings given as command-line flags (bucket, root, endpoint, profile, write_profile); see usersettings.resolve_settings
WORKERS = 8
MAX_MISSING_SHOWN = 5
MIRROR_MARKER = ".sync-roms-mirror"  # only folders holding this file are ever written to or pruned as a mirror
THEMES_PREFIX = "os/onion/Themes/"  # Onion themes in the bucket, copied to the card's Themes/
_mirror_root = None  # set once a sync reads from the local mirror instead of the bucket

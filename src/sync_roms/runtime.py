"""Process-wide settings read as `runtime.NAME` so reassignment is seen everywhere."""
import os


BUCKET = None  # set by ensure_bucket() from settings.json
ROOT = None  # folder (e.g. a mounted network share) used instead of storage; set from settings.json
ENDPOINT = None  # custom S3 endpoint URL from settings.json; None means AWS
PROFILE = os.environ.get("ROMS_PROFILE", "roms-readonly")
WRITE_PROFILE = os.environ.get("ROMS_WRITE_PROFILE", "roms")
OVERRIDES = {}  # settings given as command-line flags (bucket, root, endpoint, profile, write_profile); see usersettings.resolve_settings
WORKERS = 8
MAX_MISSING_SHOWN = 5
MIRROR_MARKER = ".sync-roms-mirror"  # only folders holding this file are ever written to or pruned as a mirror
THEMES_PREFIX = "os/onion/Themes/"  # Onion themes in storage, copied to the card's Themes/
ESDE_THEMES_PREFIX = "os/esde/themes/"  # ES-DE theme archives in storage (Art Book Next for the Surprise collection)
SPRUCE_THEMES_PREFIX = "os/spruceos/themes/"  # PyUI themes for spruce cards, one unpacked folder each
SPRUCE_THEMES_STATE = "os/spruceos/themes.json"  # {release asset: {updated_at, size, folder}}: the themes sync-roms put there
CUSTOM_THEMES_STATE = "os/spruceos/custom-themes.json"  # {folder: {files: {path: [sha256, size]}}}: the custom themes sync-roms published
APKS_PREFIX = "os/android/APKs/"  # Android APKs and the Obtainium app list in storage, copied to the card's APKs/
PICO8_PREFIX = "os/pico8/"  # the official PICO-8 zips in storage; the newest goes where each frontend installs it from
ONION_PREFIX = "os/onion/"  # the Surprise app zips for Onion cards in storage; the newest is installed under App/Surprise/
ALLIUM_PREFIX = "os/allium/"  # RAOfflineProxy for Allium cards in storage
MUOS_PREFIX = "os/muOS/"  # RAOfflineProxy for muOS cards in storage
KNULLI_PREFIX = "os/knulli/"  # RAOfflineProxy's install script for Knulli cards in storage (next to the Knulli images)
ROCKNIX_PREFIX = "os/rocknix/"  # RAOfflineProxy's install script for ROCKNIX cards in storage
SPRUCE_PREFIX = "os/spruceos/"  # spruceOS release 7z files for spruce cards in storage; the newest is staged at the card root for EZ Updater
_mirror_root = None  # set once a sync reads from the local mirror instead of storage

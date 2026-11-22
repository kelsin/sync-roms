# Device resolutions and personal boot logos on spruce cards

## Intent

Two things, the second built on the first:

1. Record every device's native pixel resolution in `devices.json`, so features that need pixel sizes have it.
2. Let a user keep their own boot logo images in their personal data folder and have sync stage the ones sized for the card's device on `spruce` cards, where spruceOS's Boot Logo app offers them.

## Goals, non-goals, anti-goals

- Goals: a `resolution` on every device with a screen; personal logos land in the folder spruce's Boot Logo app lists, on the devices where that app works or is about to.
- Non-goals: flashing the logo (always a manual pick on the device: Apps → Boot Logo → the logo → "Yes, flash"); converting, resizing or validating images (spruce fits and letterboxes any PNG or BMP itself); other firmwares; a card or global setting to turn it off; a setup guide step.
- Anti-goals: logo art, names or any personal image in the repo or in storage; touching spruce's own files in `App/BootLogo/` (its bundled logos, `bootlogo.png` the app icon, `bootlogo.bmp`).

## Constraints (from spruceOS 4.6.0 and its `Development` branch)

- The Boot Logo app lists every `*.png` and `*.bmp` in `App/BootLogo/Imgs/`; the file name without extension is the menu label. It writes a `Yes, flash <name>.<ext>` copy next to each one as its confirmation entry.
- The app runs on the Miyoo A30, Miyoo Flip and the Anbernic H700 family in 4.6.0, and on the Miyoo Mini family on `Development` (not yet released). It does not run on the MagicX Zero 40.
- The logo is stored on the device or its OS card, never on the spruce card, so staging is all sync can do.

## Approaches

- **Personal logos plus a sync step (chosen).** Logos live in the personal data folder; the repo gains only the `resolution` field and a generic copy step. Family art stays out of a repo that is the same for everyone, and any other logo can be dropped in later.
- **Generator script and art in the repo**, like `tools/gen_theme_art.py`. Rejected: puts one user's portraits and names in shared repo data.
- **Images only, copied to cards by hand.** Rejected: redone for every card.

## Design

### `resolution` in `devices.json`

- Every device with a `screen` gets `"resolution": "<W>x<H>"`, in the orientation the device is held; every device with a `screen2` also gets `"resolution2"`. Devices without `screen` (`windows-pc`, `steam-machine`) get neither.
- Values come from the research file handed to the builder (`resolutions.json`, one entry per device id). A device sold in variants records its base model (Miyoo Mini 640x480, AYANEO Pocket S 1920x1080); the Retroid Pocket Mini records the advertised 1280x960.
- A few recorded ratios are roundings of the real panel (960x544, 1334x750, 750x560 against 16:9, 16:9, 4:3). `screen` is not changed.
- Tests: every device with `screen` has a well-formed `resolution` (and `resolution2` exactly when it has `screen2`), and each resolution's ratio is within 2% of its recorded ratio.
- Docs: the `devices.json` line in CLAUDE.md. The setup guide embeds a fixed list of keys, so it is unaffected.

### Personal boot logos

- Personal data folder: `bootlogos/<W>x<H>/<name>.png|.bmp`, one folder per device resolution. Never read from or written to storage or the repo.
- New module `spruce_bootlogo.py`, called from the sync flow beside `spruce_os.install` and `spruce_settings.install`, with the same shape (returns a failure count, honours dry run).
- It acts only when all hold: the card's layout is `spruce`; the card's device is a real device (not `full`) with a `resolution`; the device is not in the module's short list of spruce devices whose Boot Logo app can't run (`magicx-zero40`); `bootlogos/<that resolution>/` has at least one logo or the card has logos sync put there earlier.
- It copies each logo to `App/BootLogo/Imgs/<name>.<ext>` on the card when the card's copy is missing or differs. `App/BootLogo/Imgs/` must already exist: when it doesn't (no spruceOS on the card yet), skip with a warning and create nothing.
- New card field `boot_logos` (in `cards.json` and its schema): the file names sync put in `Imgs/`. Only those are ever overwritten or removed. A personal logo whose name is already in `Imgs/` but not in `boot_logos` (one of spruce's own) is skipped with a warning.
- When a recorded logo is no longer in the personal folder (or the card's device changed resolution), sync removes it from `Imgs/` along with its `Yes, flash <name>.<ext>` copy, unless `--no-delete`.
- Personal file names containing `Yes, flash` are ignored, as spruce ignores them.
- After staging something new it prints a one-line hint: run Apps → Boot Logo on the device.
- Miyoo Mini cards are staged too, ahead of the spruce release that shows the app there; the files are inert until then.
- Docs: CLAUDE.md (personal data, card fields, what sync puts on a card).

### The user's logos (outside the repo)

Drawn by a one-off script, not part of this change's code: four scenes of 320x240 pixel art doubled to 640x480. The larger sizes are that same art centred on black, so pixels stay sharp: 720x480, 720x720, and 752x560 (the size the Mini Flip's panel is driven at). Written to `~/.sync-roms/bootlogos/<the device's resolution>/`, so the Mini Flip's 752x560 images go in `750x560/`, with the script kept beside them.

## My calls (not decided by the user)

- Field names `resolution`, `resolution2`, `boot_logos`; folder name `bootlogos/`; module name.
- Choosing logos by the device's panel resolution. Spruce reads the real logo size from the device at flash time and letterboxes, so a mismatch (a stock CubeXX carries a 640x480 logo on a 720x720 panel) costs sharpness, not correctness.
- The unsupported-device list lives in the module, not in `devices.json`: it is a fact about spruce's app, used in one place.
- All logos for the resolution go on every eligible card; the user picks on the device.
- Only lowercase `.png` and `.bmp` are taken, as the app lists only those; the clash check against spruce's own names ignores case, since the card is FAT.
- A card that stops being eligible (another layout, `full`, the Zero 40) keeps its staged logos and its `boot_logos`.
- `boot_logos` is treated like `drivers` everywhere sync-written card fields are listed: the schema, `check`'s shape validation, card export and import.

## Left to the builder

Message wording, where exactly the call sits in the sync flow, how "differs" is checked (the files are a few KB), tests (eligibility, copy, skip on spruce's own name, cleanup, `--no-delete`, dry run, missing `Imgs/`), README changes if `tests/test_readme.py` asks for any.

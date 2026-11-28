## Format contract v1

Both repos implement against this. Freeze it first and change it only by bumping `formatVersion`.

### Theme folder

```
Themes/Pixel/
  config.json, config_WxH.json …   ← default palette's colors (valid for old PyUI)
  skin/, skin_WxH/, icons/, icons_WxH/ …  ← default variant + default palette
  preview.png
  options/
    manifest.json                  ← opt-in marker + all metadata
    applied.json                   ← what the top-level files currently show (shipped = defaults)
    selected.json                  ← the user's choice (NOT shipped; written on device / by sync-roms)
    variants/<id>/<relpath>        ← every variant-specific file, for EVERY variant incl. default
    templates/<relpath>.tpl        ← one per palette-dependent image, per resolution folder
```

### `options/manifest.json`

```json
{
  "formatVersion": 1,
  "variants": {
    "default": "consoles",
    "list": [ {"id": "consoles", "name": "Consoles"}, {"id": "controllers", "name": "Controllers"} ]
  },
  "colors": {
    "roles": [ {"id": "text", "name": "Text"}, {"id": "list", "name": "List"},
               {"id": "selected", "name": "Selected"}, {"id": "accent", "name": "Accent"},
               {"id": "dim", "name": "Dim"}, {"id": "bar", "name": "Bar"} ],
    "configKeys": {
      "title.color": "text", "hint.color": "text", "batteryPercentage.color": "text",
      "currentpage.color": "text", "total.color": "accent", "grid.color": "dim",
      "grid.selectedcolor": "accent", "list.color": "list", "list.selectedcolor": "selected",
      "screensaver.widgets[type=clock].color": "selected",
      "screensaver.widgets[type=date].color": "text",
      "screensaver.widgets[type=battery].color": "accent"
    },
    "igmKeys": {},
    "defaultPalette": "Gruvbox",
    "palettes": [ {"name": "Gruvbox", "colors": {"text": "#…", "list": "#…", "selected": "#…",
                                                  "accent": "#…", "dim": "#…", "bar": "#…"}} ]
  }
}
```

- **Path syntax for `configKeys`:** dotted keys, plus `name[field=value]` to choose an item in a list.
- **Which files the key map applies to:** every `config*.json`.
- **Either section is optional:** a theme can ship only `variants` or only `colors`.

### `selected.json` / `applied.json`

```json
{ "variant": "controllers", "palette": "Nord", "colors": { "bar": "#3b4252", … } }
```

- **`colors`** always holds all role values, so custom edits survive.
- **`palette`** is the preset name, or `null` once the user edits a color.
- **Re-apply rule:** re-apply whenever `selected.json` differs from `applied.json`.
- **Why this survives reinstalls:** the archive ships `applied.json` = defaults and never ships `selected.json`. A `-aoa` reinstall therefore resets the files and `applied.json` together, and the user's choice survives and is re-applied.

### Template `.tpl` v2 (magic `PUT2`)

This extends Accent Color's `NUTP` format. Here is a recommended layout; implementers may adjust it before the format is frozen.

```
magic  b"PUT2"
u16    width, height, entry_count, flags        (little endian; flags bit0 = 2-byte index)
entry_count × 8 bytes:   (superseded, see Amendment 1: entries are 10 bytes)
  alpha, kind, role, target, t, r, g, b
    kind 0 = fixed rgb (r,g,b)
    kind 1 = role color mixed toward target by t/255   (superseded, see Amendments 1 and 2: t is in thousandths)
             target 0 = none, 1 = white, 2 = black, 3 = fixed rgb (r,g,b)
rest   zlib-compressed index per pixel (u8, or u16 when flags bit0)
```

- **Role indexes** are positions in `manifest.colors.roles`.
- **Pixel shades map directly to entries:** `hi` = (bar, white, 89), `sh` = (bar, black, 102), `mid` = (bar, black, 115), `dark` = (bar, black, 179), `ink` = fixed. (superseded by the amended units: `hi` = (bar, white, 350), `sh` = (bar, black, 400), `mid` = (bar, black, 450), `dark` = (bar, black, 700), `ink` = fixed; the unselected key's darker shade is a kind-2 entry (dark, black, 500).) Rounding must match `frames._mix`.
- **Where the output goes:** the target file is the `.tpl` path with `templates/` stripped and `.tpl` removed.

### Apply algorithm (device)

1. Copy `options/variants/<selected>/**` over the top level.
2. Render every `options/templates/**.tpl` with `selected.colors` and write each one atomically.
3. Patch `configKeys` in every `config*.json`, and `igmKeys` in `igm.json` if present.
4. Write `applied.json` = `selected.json` last, so an interrupted apply re-runs.
5. Delete PyUI's own resized copies (see Amendment 7).
6. Restart PyUI.

## Amendments to contract v1

Each is **Amended** relative to the contract above and wins over it.

1. **Amended: entries are 10 bytes**: `alpha u8, kind u8, src u16, target u8, t u16, r u8, g u8, b u8` (little endian, struct `<BBHBHBBB`). `t` is in thousandths: the mix amount is the float `t / 1000`. (`t/255` can't reproduce `.35`, `.45`, `.5`, `.7`: dozens of channel values round differently.)
2. **Amended: kind 2** = entry `src` (an earlier entry, `src` < this entry's index) mixed toward `target` by `t/1000`. Kind 1's `src` is the role index. Kind 0 ignores `src`/`target`/`t`. (The unselected key mixes `dark` toward black again: two roundings.)
3. **Amended: mixing is exactly** `round(a + (b - a) * t)` per channel with Python's `round` (half to even), `a` the source channel, `b` the target channel; `target 0` (none) means the source colour itself.
4. **Amended: `igmKeys` values** are `{"role": "<id>", "suffix": "FF"}` objects (igm.json colours are 8-digit `#RRGGBBAA`); `configKeys` values stay plain role ids.
5. **Amended: shipped `applied.json` re-apply after a theme update**: when sync-roms copies a changed `options/` file to a card it also copies storage's top-level files and `applied.json` (the defaults), so the device re-applies the user's `selected.json` on next boot.
6. **Amended: path syntax of `configKeys`/`igmKeys`** (sync-roms' `recolor.set_path`): keys are dot-separated. `name[field=value]` selects the list `name` and applies the rest of the path to every item that is an object whose `field` equals the string `value` (items that aren't objects or don't match are skipped). The last key is set whenever its parent object exists, created if it is missing; nothing else is ever created, and a missing parent (key, list or non-object) is skipped without error.
7. **Amended: PyUI's resized copies**: PyUI makes `config_<W>x<H>.json`, `skin_<W>x<H>/` and `icons_<W>x<H>/` at the top level once and never remakes them, so copies it made keep the old colours. After applying (before restarting PyUI), delete each such top-level entry for which `options/templates/skin_<W>x<H>/` does not exist; PyUI remakes it from the freshly applied files. Every `skin_<W>x<H>/` the Pixel theme ships has templates there, so shipped copies are kept; a shipped `icons_<W>x<H>/` or `config_<W>x<H>.json` of a size with no templates would also be deleted, which is harmless because PyUI remakes it from the applied files.

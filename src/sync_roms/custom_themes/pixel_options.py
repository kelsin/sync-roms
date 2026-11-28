"""The "Pixel" spruceOS theme: Pixel Consoles in Gruvbox, carrying both variants and every palette as data in options/
(docs/theme-options-format.md), so the device switches them without another theme."""
import json
import os
import shutil
import tempfile

from . import palettes, templates
from .pixel import recipe, recolor
from .pixel.build import build_theme

STYLE = "Pixel"
BASE = "SPRUCE"
PALETTES = False
OPTIONS = True
DEFAULT_VARIANT = "consoles"
DEFAULT_PALETTE = "Gruvbox"
assert "#%02X%02X%02X" % recolor.BAR_GRAY == palettes.get(DEFAULT_PALETTE).bar.upper()  # the bar templates are read from the default build
VARIANTS = {"consoles": ("Consoles", "CONSOLES"), "controllers": ("Controllers", "CONTROLLERS")}
DESCRIPTION = "Pixel-art consoles or controllers on black, in any palette."


def _files(root):
    """{relative path with /: absolute path} of every file under root."""
    out = {}
    for dirpath, _, files in os.walk(root):
        for file in files:
            path = os.path.join(dirpath, file)
            out[os.path.relpath(path, root).replace(os.sep, "/")] = path
    return out


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _was_drawn(rel, drawn):
    """Whether the build drew rel: a drawn file or its pre-scaled copy (build.resize_variants)."""
    folder, _, rest = rel.partition("/")
    base, _, size = folder.partition("_")
    return rel in drawn or (size and folder != "skin_640_480" and f"{base}/{rest}" in drawn)


def _colors(palette):
    return {role: getattr(palette, role) for role in recipe.ROLES}


def manifest():
    return {
        "formatVersion": 1,
        "variants": {"default": DEFAULT_VARIANT, "list": [{"id": v, "name": n} for v, (n, _) in VARIANTS.items()]},
        "colors": {
            "roles": [{"id": role, "name": role.capitalize()} for role in recipe.ROLES],
            "configKeys": recolor.CONFIG_KEYS,
            "igmKeys": recolor.IGM_KEYS,
            "defaultPalette": DEFAULT_PALETTE,
            "palettes": [{"name": p.name, "colors": _colors(p)} for p in palettes.PALETTES.values()],
        },
    }


def build(base_dir, out_dir):
    """Write <out_dir>/Pixel/ (replacing it) and return that path."""
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, STYLE)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    palette = palettes.get(DEFAULT_PALETTE)
    recipes, drawn = {}, set()
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        builds = {}
        for variant, (_, kind) in VARIANTS.items():
            default = variant == DEFAULT_VARIANT
            builds[variant] = build_theme(base_dir, os.path.join(tmp, variant), STYLE, kind, palette,
                                          recipes=recipes if default else None, description=DESCRIPTION,
                                          drawn=drawn if default else None)
        files = {variant: _files(folder) for variant, folder in builds.items()}
        paths = set().union(*files.values())
        variant_files = sorted(
            rel for rel in paths
            if not (rel.rsplit("/", 1)[-1].startswith("config") and rel.endswith(".json"))
            and len({_read(f[rel]) if rel in f else None for f in files.values()}) > 1)
        options = os.path.join(builds[DEFAULT_VARIANT], "options")
        for variant in VARIANTS:
            for rel in variant_files:
                _write(os.path.join(options, "variants", variant, *rel.split("/")), _read(files[variant][rel]))
        tpls = {rel: templates.from_canvas(canvas) for rel, canvas in recipes.items()}
        for rel, path in files[DEFAULT_VARIANT].items():
            if (rel.startswith("skin") and "/" in rel and rel.lower().endswith(".png") and rel not in tpls
                    and not _was_drawn(rel, drawn)):
                data = templates.from_bar_image(path)
                if data is not None:
                    tpls[rel] = data
        for rel, data in sorted(tpls.items()):
            if rel not in variant_files:
                _write(os.path.join(options, "templates", *f"{rel}.tpl".split("/")), data)
        for file, data in (("manifest.json", manifest()),
                           ("applied.json", {"variant": DEFAULT_VARIANT, "palette": palette.name,
                                             "colors": _colors(palette)})):
            with open(os.path.join(options, file), "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
        shutil.move(builds[DEFAULT_VARIANT], dest)
    return dest

"""The custom themes' color palettes: each built theme is one style in one palette, named `<style> - <palette>`."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    name: str
    text: str
    list: str
    selected: str
    accent: str
    dim: str
    bar: str


# name: (text, list, selected, accent, dim, bar)
_DATA = {
    "Gruvbox":      ("#EBDBB2", "#FBF1C7", "#FBF1C7", "#D65D0E", "#7C6F64", "#504945"),
    "Arcade":       ("#F6F3FF", "#A9ABC4", "#FFD43F", "#FFD43F", "#62647F", "#342E78"),
    "Candy":        ("#F6F3FF", "#C9B8E8", "#FF7FB8", "#FF7FB8", "#6A5C8F", "#4A2F6B"),
    "Mint":         ("#F6F3FF", "#9FD8D0", "#4FE0CF", "#43C8F0", "#4B6F72", "#1F4A52"),
    "Game Boy":     ("#9BBC0F", "#8BAC0F", "#E0F8D0", "#E0F8D0", "#306230", "#306230"),
    "Pocket":       ("#E8E8E0", "#B8B8B0", "#FFFFFF", "#FFFFFF", "#707068", "#484840"),
    "GBA Indigo":   ("#E8E4FF", "#B4ACE0", "#FFFFFF", "#8CF06C", "#6A5FA8", "#3E2F8A"),
    "GBA Glacier":  ("#EAF6FF", "#A8D4EC", "#FFFFFF", "#7FD0F0", "#5A86A0", "#2C6A8E"),
    "GBA Fuchsia":  ("#FFE8F4", "#F0A8D0", "#FFFFFF", "#FF5AB4", "#9A5A80", "#A0306E"),
    "GBA Flame":    ("#FFE8E0", "#E8B0A0", "#FFFFFF", "#FF6A3A", "#8A4A40", "#B02418"),
    "GBA Cobalt":   ("#E4EAFF", "#A8B4E0", "#FFFFFF", "#C0C8D8", "#5A6488", "#1F3A8C"),
    "GBA Platinum": ("#F0F0F4", "#C0C4CC", "#FFFFFF", "#9A8CF0", "#70747C", "#4A4E58"),
    "Virtual Boy":  ("#FF3030", "#B02020", "#FF8080", "#FF8080", "#601010", "#400808"),
    "Famicom":      ("#F1E4C3", "#D8C9A3", "#FFFFFF", "#EE4B3F", "#8C5B3C", "#A3303F"),
    "NES":          ("#E8E8E8", "#B0B0B0", "#FFFFFF", "#EE4B3F", "#707070", "#8B2A2A"),
    "SNES":         ("#E4E0F4", "#B7B0D8", "#FFFFFF", "#A66BE2", "#6D668F", "#5B50D8"),
    "Genesis":      ("#F6F3FF", "#9A9BB5", "#FFFFFF", "#EE4B3F", "#4A4C66", "#1F3F9E"),
    "Dreamcast":    ("#FFFFFF", "#C7D0DA", "#FFFFFF", "#F7992A", "#6A7788", "#E06A10"),
    "PlayStation":  ("#E8ECF2", "#AEB6C4", "#FFFFFF", "#43C8F0", "#68707F", "#35507A"),
    "Neo Geo":      ("#FFD43F", "#E8C23A", "#FFFFFF", "#EE4B3F", "#8C7A25", "#3A2A00"),
    "PICO-8":       ("#FFF1E8", "#C2C3C7", "#FFEC27", "#FF77A8", "#5F574F", "#1D2B53"),
    "Commodore":    ("#A0A0FF", "#7C70DA", "#FFFFFF", "#7C70DA", "#4A3FA0", "#352879"),
    "Amber CRT":    ("#FFB000", "#CC8C00", "#FFD060", "#FFD060", "#6B4A00", "#3A2800"),
    "Green CRT":    ("#33FF33", "#22C022", "#B8FFB8", "#B8FFB8", "#0F6B0F", "#083A08"),
    "Nord":         ("#ECEFF4", "#D8DEE9", "#FFFFFF", "#88C0D0", "#4C566A", "#434C5E"),
    "Dracula":      ("#F8F8F2", "#BDC0D4", "#FFFFFF", "#FF79C6", "#6272A4", "#44475A"),
    "Solarized":    ("#EEE8D5", "#93A1A1", "#FDF6E3", "#B58900", "#586E75", "#073642"),
    "Synthwave":    ("#F6F3FF", "#C8A8F0", "#FF4FD8", "#2DE2E6", "#6A4C93", "#3A1C71"),
    "Sunset":       ("#FFE8D6", "#F2C4A0", "#FFFFFF", "#FF8C42", "#8A5A5A", "#6B2D5C"),
    "Ocean":        ("#E0F4FF", "#9CCFE8", "#FFFFFF", "#3DB5FF", "#4A7088", "#14405E"),
    "Sakura":       ("#FFF0F5", "#F4C7D8", "#FFFFFF", "#FF7FB8", "#9A6B80", "#7A3A5A"),
    "Forest":       ("#E8F4DC", "#A8D08D", "#FFFFFF", "#FFD43F", "#5E7F4A", "#2D5A2D"),
    "Grape":        ("#F0E6FF", "#C4A8F0", "#FFFFFF", "#FFD43F", "#7A5CAE", "#5B2A9E"),
    "Jigglypuff":   ("#FFE8F2", "#F4B8D0", "#FFFFFF", "#5CC8D8", "#9A6880", "#B8487A"),
    "Pikachu":      ("#FFF4C0", "#F0D060", "#FFFFFF", "#F04838", "#8C7428", "#B08A00"),
    "Snorlax":      ("#F4E8C8", "#D8C8A0", "#FFFFFF", "#F0E0B8", "#4F7A88", "#1F5068"),
    "Bulbasaur":    ("#E0F8E8", "#90D8B0", "#FFFFFF", "#E85050", "#4F8A70", "#2E7058"),
    "Charmander":   ("#FFF0D8", "#F8C890", "#FFFFFF", "#FFD030", "#9A5A30", "#C04E18"),
    "Squirtle":     ("#E8F6FF", "#A0D8F0", "#FFFFFF", "#E89A48", "#5080A0", "#2E78A8"),
    "Eevee":        ("#FFF4E0", "#E8C8A0", "#FFFFFF", "#F8E0B0", "#8A6040", "#7A4A20"),
    "Monochrome":   ("#FFFFFF", "#BBBBBB", "#FFFFFF", "#FFFFFF", "#666666", "#333333"),
}

PALETTES = {name: Palette(name, *colors) for name, colors in _DATA.items()}


def get(name):
    """The palette called name; KeyError for an unknown one."""
    return PALETTES[name]


def names():
    return list(PALETTES)

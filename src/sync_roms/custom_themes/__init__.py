"""Custom spruceOS themes sync-roms builds from a base theme. THEMES maps each theme's name to its module."""
from . import pixel_consoles, pixel_controllers

THEMES = {module.NAME: module for module in (pixel_consoles, pixel_controllers)}


def names():
    return sorted(THEMES, key=str.lower)

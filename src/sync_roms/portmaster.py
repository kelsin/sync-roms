"""PortMaster on spruce: the card paths it uses and which devices and systems it covers."""

PORTS = "ports"  # the system id and storage folder of the port zips
CONTROL = "Persistent/portmaster/PortMaster"
AUTOINSTALL = CONTROL + "/autoinstall"
LIBS = CONTROL + "/libs"


def enabled(device, layout_name):
    """Whether PortMaster is set up on this card: a spruce card of a device flagged "portmaster"."""
    return layout_name == "spruce" and bool(device) and device.get("portmaster") is True


def owns_folder(system):
    """Whether PortMaster owns the system's ROM folder: sync never sweeps, cleans or prunes it, on any layout."""
    return system["bucket"] == PORTS

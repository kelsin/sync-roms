"""ES-DE/Knulli custom collection files."""

_DROPPED = '*",./:;<>\\|\n\t\r'  # characters ES-DE rejects in a collection name


def safe_name(name):
    """name without the characters ES-DE rejects in a collection name, trimmed."""
    return "".join(c for c in name if c not in _DROPPED).strip()

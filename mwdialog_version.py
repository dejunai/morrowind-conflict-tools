"""Single source of truth for the package version. Credit: dej (dejunai)."""

__version__ = "0.93-beta"


def version_label(tool=None):
    """'Morrowind Conflict Tools 0.93-beta', optionally with the tool name in parentheses."""
    base = f"Morrowind Conflict Tools {__version__}"
    return f"{base} ({tool})" if tool else base

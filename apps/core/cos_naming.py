"""
CoS Naming — Single source of truth for Chief of Staff display names.

Usage:
    from apps.core.cos_naming import CoSNaming

    # In global/system content (docs, release notes, help):
    label = CoSNaming.SYSTEM  # "Chief of Staff"

    # In user-facing conversation:
    label = CoSNaming.display(user)  # returns user's custom name or "Chief of Staff"
"""


class CoSNaming:
    """Centralised naming for the Chief of Staff persona."""

    SYSTEM = "Chief of Staff"

    @staticmethod
    def display(user):
        """Return the user's chosen CoS name, or the system default."""
        prefs = getattr(user, 'preferences', None)
        if prefs is not None:
            name = getattr(prefs, 'cos_display_name', '')
            if name and name.strip():
                return name.strip()
        return CoSNaming.SYSTEM

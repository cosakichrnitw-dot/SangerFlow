"""Shared presentation colors for canonical DNA base identities.

These colors are deliberately limited to *base identity*.  Selection,
manual-edit, conflict, exclusion, quality, and review-state colors remain
viewer-owned state styling and must not be inferred from this palette.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from PySide6.QtGui import QColor


# Use the same values for chromatogram channels, base letters, and sequence
# cell backgrounds so an A/C/G/T keeps one visual identity throughout Studio.
BASE_IDENTITY_HEX: Mapping[str, str] = MappingProxyType(
    {
        "A": "#e06666",  # red
        "C": "#7bc67b",  # green
        "G": "#8e5ba6",  # purple
        "T": "#6fa8dc",  # blue
    }
)

BASE_IDENTITY_COLORS: Mapping[str, QColor] = MappingProxyType(
    {base: QColor(value) for base, value in BASE_IDENTITY_HEX.items()}
)


def base_identity_color(base: object, *, fallback: str = "#666666") -> QColor:
    """Return a fresh QColor for a canonical base or a presentation fallback."""

    key = str(base).upper()
    color = BASE_IDENTITY_COLORS.get(key)
    return QColor(color) if color is not None else QColor(fallback)


def base_identity_colors() -> dict[str, QColor]:
    """Return a mutable copy for Qt paint loops without exposing shared state."""

    return {base: QColor(color) for base, color in BASE_IDENTITY_COLORS.items()}

"""Regression checks for Studio's canonical base-identity palette."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.qt_runtime import configure_qt_plugins

configure_qt_plugins()

from PySide6.QtGui import QColor
from widgets.base_palette import BASE_IDENTITY_COLORS, BASE_IDENTITY_HEX, base_identity_color
from widgets.sequence_grid import (
    DEFAULT_SEQUENCE_GRID_PALETTE,
    SEQUENCE_GRID_EDITED_BACKGROUND,
    SEQUENCE_GRID_SELECTION_OUTLINE,
)
from widgets.viewers.alignment_chromatogram_viewer import _BASE_COLORS as ALIGNMENT_BASE_COLORS
from widgets.viewers.alignment_chromatogram_viewer import _TRACE_COLORS as ALIGNMENT_TRACE_COLORS
from widgets.viewers.alignment_chromatogram_viewer import _base_color as alignment_base_color
from widgets.viewers.chromatogram_viewer import _BASE_COLORS as CHROMATOGRAM_BASE_COLORS
from widgets.viewers.chromatogram_viewer import _TRACE_COLORS as CHROMATOGRAM_TRACE_COLORS
from widgets.viewers.consensus_review_viewer import _base_color as consensus_base_color
from widgets.viewers.pair_consensus_chromatogram import _TRACE_COLORS as PAIR_TRACE_COLORS


_EXPECTED = {
    "A": "#e06666",
    "C": "#7bc67b",
    "G": "#8e5ba6",
    "T": "#6fa8dc",
}


def _hex_map(colors: object) -> dict[str, str]:
    return {base: colors[base].name() for base in "ACGT"}


class BasePaletteTests(unittest.TestCase):
    def test_canonical_base_identity_palette_is_explicit(self) -> None:
        self.assertEqual(dict(BASE_IDENTITY_HEX), _EXPECTED)
        self.assertEqual(_hex_map(BASE_IDENTITY_COLORS), _EXPECTED)
        self.assertEqual(base_identity_color("G").name(), _EXPECTED["G"])

    def test_major_chromatogram_and_consensus_presentations_share_identity_colors(self) -> None:
        for colors in (
            CHROMATOGRAM_TRACE_COLORS,
            CHROMATOGRAM_BASE_COLORS,
            ALIGNMENT_TRACE_COLORS,
            ALIGNMENT_BASE_COLORS,
            PAIR_TRACE_COLORS,
        ):
            self.assertEqual(_hex_map(colors), _EXPECTED)
        for base, expected in _EXPECTED.items():
            self.assertEqual(alignment_base_color(base).name(), expected)
            self.assertEqual(consensus_base_color(base).name(), expected)

    def test_sequence_grid_backgrounds_share_identity_without_reusing_state_colors(self) -> None:
        self.assertEqual(_hex_map(DEFAULT_SEQUENCE_GRID_PALETTE.base_backgrounds), _EXPECTED)
        identity_values = set(_EXPECTED.values())
        self.assertNotIn(SEQUENCE_GRID_EDITED_BACKGROUND.name(), identity_values)
        self.assertNotIn(SEQUENCE_GRID_SELECTION_OUTLINE.name(), identity_values)
        self.assertNotIn(DEFAULT_SEQUENCE_GRID_PALETTE.excluded_overlay.name(), identity_values)
        # Alignment/pair chromatogram selection and old consensus-review
        # change highlighting are state overlays, not base identities.
        self.assertNotIn(QColor("#7B3FBF").name(), identity_values)
        self.assertNotIn(QColor("#FFD966").name(), identity_values)

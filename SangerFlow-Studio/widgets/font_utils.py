"""Platform-native monospaced fonts for scientific grid/viewer rendering."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase


def fixed_width_font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Return Qt's system fixed-width font without assuming platform font names."""

    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(size)
    font.setWeight(weight)
    font.setStyleHint(QFont.StyleHint.TypeWriter)
    return font

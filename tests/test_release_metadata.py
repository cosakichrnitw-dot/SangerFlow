"""Consistency checks for the v1.0 public-release metadata."""

from __future__ import annotations

import re
from pathlib import Path

from core.version import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_consistent_across_public_metadata() -> None:
    pyproject_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    spec_text = (ROOT / "packaging/macos/SangerFlow-Studio.spec").read_text(
        encoding="utf-8"
    )

    assert __version__ == "1.0.0"
    assert re.search(rf'^version = "{re.escape(__version__)}"$', pyproject_text, re.MULTILINE)
    assert re.search(
        rf'"CFBundleShortVersionString": "{re.escape(__version__)}"', spec_text
    )
    assert re.search(rf'"CFBundleVersion": "{re.escape(__version__)}"', spec_text)


def test_citation_metadata_matches_release_version_and_author() -> None:
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")

    assert "version: 1.0.0" in citation
    assert "given-names: Chihiro" in citation
    assert "family-names: Osaki" in citation

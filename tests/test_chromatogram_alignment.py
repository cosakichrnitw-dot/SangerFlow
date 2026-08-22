"""Regression tests for Studio-exposed MAFFT command settings."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from core.chromatogram_alignment import align_reads


class _Read:
    filename = "sample.ab1"
    trimmed_sequence = "ATGC"


def test_align_reads_keeps_default_auto_command() -> None:
    with patch("core.chromatogram_alignment.shutil.which", return_value="/fake/mafft"), patch("core.chromatogram_alignment.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="")) as run, patch(
        "core.chromatogram_alignment.AlignIO.read", return_value="alignment"
    ):
        assert align_reads([_Read()]) == "alignment"

    assert run.call_args.args[0] == ["/fake/mafft", "--auto", "-"]


def test_align_reads_maps_advanced_settings_to_real_mafft_options() -> None:
    with patch("core.chromatogram_alignment.shutil.which", return_value="/fake/mafft"), patch("core.chromatogram_alignment.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="")) as run, patch(
        "core.chromatogram_alignment.AlignIO.read", return_value="alignment"
    ):
        align_reads(
            [_Read()],
            strategy="L-INS-i",
            gap_opening_penalty=1.7,
            offset=0.2,
            maxiterate=500,
            adjust_direction=True,
        )

    assert run.call_args.args[0] == [
        "/fake/mafft", "--localpair", "--op", "1.7", "--ep", "0.2", "--maxiterate", "500",
        "--adjustdirection", "-",
    ]

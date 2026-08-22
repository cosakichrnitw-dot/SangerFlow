"""BOLD identification service boundary for SangerFlow v1.0.

The current BOLD Portal APIs documented by BOLD expose barcode record search
and download endpoints.  SangerFlow does not automate the interactive Barcode
ID web page or legacy unsupported endpoints.  This module therefore provides a
clear unavailable runner that preserves the runner-based architecture until a
supported programmatic identification API is available.
"""

from __future__ import annotations


class BoldIdentificationUnavailableError(RuntimeError):
    """Raised when no supported BOLD identification API is configured."""


class BoldIdentificationRunner:
    """Safe placeholder for future supported BOLD programmatic ID services."""

    message = (
        "BOLD Identification is not connected to a supported programmatic API. "
        "The current BOLD Portal APIs support record search/download, while the "
        "Barcode ID Engine is an interactive service. SangerFlow will not "
        "scrape the web UI or use unsupported legacy endpoints."
    )

    def __call__(self, sequence: str) -> object:
        raise BoldIdentificationUnavailableError(self.message)

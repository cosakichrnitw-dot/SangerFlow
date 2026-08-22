"""Studio presentation metrics for read quality values.

This module intentionally leaves core quality semantics untouched.  The Studio
default HQ% is explicitly the percentage of raw qualities at or above Q40.
"""

from __future__ import annotations


DEFAULT_HQ_THRESHOLD = 40


def quality_percent_at_or_above(read_like: object | None, threshold: float = DEFAULT_HQ_THRESHOLD) -> float | None:
    """Return the raw-quality percentage at or above *threshold*, or None."""

    if read_like is None:
        return None
    rate_function = getattr(read_like, "quality_rate_at_or_above", None)
    if callable(rate_function):
        return float(rate_function(threshold))
    quality = tuple(getattr(read_like, "quality", ()) or ())
    if not quality:
        return None
    return 100.0 * sum(value >= threshold for value in quality) / len(quality)


def format_hq_percent(read_like: object | None, threshold: float = DEFAULT_HQ_THRESHOLD) -> str:
    """Format the shared Studio HQ% value for compact tables."""

    value = quality_percent_at_or_above(read_like, threshold)
    return "—" if value is None else f"{value:.1f}%"

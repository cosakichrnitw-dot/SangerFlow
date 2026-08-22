"""Shared, display-only geometry for chromatograms on alignment columns.

The helpers consume an already-established mapping from alignment column to
raw trace peak position.  They do not align reads, call consensus, reverse a
read, or alter any scientific model.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath


@dataclass(frozen=True)
class AlignmentTracePoint:
    x: float
    signal: int
    left_alignment_column: int
    right_alignment_column: int
    trace_position: int


def alignment_column_x(
    alignment_column: int,
    *,
    left_margin: int,
    column_width: int,
) -> int:
    return left_margin + (alignment_column - 1) * column_width


def peak_to_peak_trace_segments(
    mapping: dict[int, int | None],
    trace: tuple[int, ...],
    *,
    left_margin: int,
    column_width: int,
    first_col: int = 1,
    last_col: int | None = None,
) -> tuple[tuple[AlignmentTracePoint, ...], ...]:
    """Keep raw samples between adjacent mapped peaks; break at gaps."""

    if last_col is None:
        last_col = max(mapping, default=0)
    if not trace:
        return ()
    max_column = max(mapping, default=0)
    pair_start = max(1, first_col - 1)
    pair_end = min(max_column - 1, last_col)
    segments: list[tuple[AlignmentTracePoint, ...]] = []
    current: list[AlignmentTracePoint] = []
    for left_column in range(pair_start, pair_end + 1):
        right_column = left_column + 1
        left_trace_pos = mapping.get(left_column)
        right_trace_pos = mapping.get(right_column)
        if left_trace_pos is None or right_trace_pos is None:
            if len(current) >= 2:
                segments.append(tuple(current))
            current = []
            continue
        interval = _peak_to_peak_trace_points(
            left_column,
            int(left_trace_pos),
            right_column,
            int(right_trace_pos),
            trace,
            left_margin=left_margin,
            column_width=column_width,
        )
        if len(interval) < 2:
            continue
        if current and current[-1].trace_position == interval[0].trace_position:
            current.extend(interval[1:])
        else:
            if len(current) >= 2:
                segments.append(tuple(current))
            current = list(interval)
    if len(current) >= 2:
        segments.append(tuple(current))
    return tuple(segments)


def raw_trace_path(
    segment: tuple[AlignmentTracePoint, ...],
    *,
    x_offset: int,
    y_base: float,
    gain: float,
) -> QPainterPath:
    path = QPainterPath()
    if not segment:
        return path
    first = segment[0]
    path.moveTo(QPointF(first.x - x_offset, y_base - first.signal * gain))
    for point in segment[1:]:
        path.lineTo(QPointF(point.x - x_offset, y_base - point.signal * gain))
    return path


def _peak_to_peak_trace_points(
    left_alignment_column: int,
    left_trace_position: int,
    right_alignment_column: int,
    right_trace_position: int,
    trace: tuple[int, ...],
    *,
    left_margin: int,
    column_width: int,
) -> tuple[AlignmentTracePoint, ...]:
    left_trace_position = max(0, min(len(trace) - 1, left_trace_position))
    right_trace_position = max(0, min(len(trace) - 1, right_trace_position))
    if left_trace_position == right_trace_position:
        return (
            AlignmentTracePoint(
                x=alignment_column_x(
                    left_alignment_column,
                    left_margin=left_margin,
                    column_width=column_width,
                ),
                signal=int(trace[left_trace_position]),
                left_alignment_column=left_alignment_column,
                right_alignment_column=right_alignment_column,
                trace_position=left_trace_position,
            ),
        )
    step = 1 if right_trace_position > left_trace_position else -1
    raw_span = right_trace_position - left_trace_position
    left_x = alignment_column_x(
        left_alignment_column, left_margin=left_margin, column_width=column_width
    )
    right_x = alignment_column_x(
        right_alignment_column, left_margin=left_margin, column_width=column_width
    )
    return tuple(
        AlignmentTracePoint(
            x=left_x + ((position - left_trace_position) / raw_span) * (right_x - left_x),
            signal=int(trace[position]),
            left_alignment_column=left_alignment_column,
            right_alignment_column=right_alignment_column,
            trace_position=position,
        )
        for position in range(left_trace_position, right_trace_position + step, step)
    )

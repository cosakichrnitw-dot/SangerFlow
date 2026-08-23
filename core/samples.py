"""Sample-level grouping for already loaded Sanger reads.

This module is deliberately independent from the GUI and does not change a
``SangerRead``.  It provides a conservative filename-based classification
snapshot that later workflows may consume.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
from typing import Iterable, Optional

from core.models import SangerRead


class ReadOrientation(str, Enum):
    """Orientation inferred from a filename suffix."""

    FORWARD = "FORWARD"
    REVERSE = "REVERSE"
    UNSPECIFIED = "UNSPECIFIED"


class SampleClassification(str, Enum):
    """Top-level shape of a sample after filename grouping."""

    SINGLE = "SINGLE"
    PAIR = "PAIR"
    AMBIGUOUS = "AMBIGUOUS"


class PairingStatus(str, Enum):
    """Reason a sample is or is not safe for automatic pair assembly."""

    CLEAR_PAIR = "CLEAR_PAIR"
    # ``SINGLE_FORWARD`` remains a compatibility alias for callers using the
    # pre-v1.0 spelling.  New code receives the explicit orphan semantic.
    ORPHAN_FORWARD = "ORPHAN_FORWARD"
    SINGLE_FORWARD = "ORPHAN_FORWARD"
    SINGLE_UNSPECIFIED = "SINGLE_UNSPECIFIED"
    ORPHAN_REVERSE = "ORPHAN_REVERSE"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class Sample:
    """A filename-classified group of one or more ``SangerRead`` objects.

    ``PAIR`` is returned only when exactly one explicitly named Forward read
    and one explicitly named Reverse read share a sample identifier.  A lone
    Forward read is a valid ``SINGLE`` sample.  A filename with no recognised
    orientation suffix is also a valid single sample, but its orientation is
    recorded as ``UNSPECIFIED`` rather than guessed.
    """

    sample_id: str
    classification: SampleClassification
    pairing_status: PairingStatus
    forward_read: Optional[SangerRead] = None
    reverse_read: Optional[SangerRead] = None
    unspecified_reads: tuple[SangerRead, ...] = ()
    forward_candidates: tuple[SangerRead, ...] = ()
    reverse_candidates: tuple[SangerRead, ...] = ()
    unspecified_candidates: tuple[SangerRead, ...] = ()
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Expose every classified input read without changing legacy fields.

        ``forward_read`` and ``reverse_read`` remain the unique, automatically
        safe pair members.  Candidate tuples preserve all reads for a future
        explicit-resolution UI, including ambiguous groups.
        """

        forward = _unique_reads(
            self.forward_candidates or ((self.forward_read,) if self.forward_read else ())
        )
        reverse = _unique_reads(
            self.reverse_candidates or ((self.reverse_read,) if self.reverse_read else ())
        )
        unspecified = _unique_reads(
            self.unspecified_candidates or self.unspecified_reads
        )
        object.__setattr__(self, "forward_candidates", forward)
        object.__setattr__(self, "reverse_candidates", reverse)
        object.__setattr__(self, "unspecified_candidates", unspecified)
        # Retain the original public attribute for backwards compatibility.
        object.__setattr__(self, "unspecified_reads", unspecified)

    @property
    def reads(self) -> tuple[SangerRead, ...]:
        """All reads in a stable display order: Forward, Reverse, then rest."""

        reads = []

        reads.extend(self.forward_candidates)
        reads.extend(self.reverse_candidates)
        reads.extend(self.unspecified_candidates)

        return tuple(reads)

    @property
    def is_clear_pair(self) -> bool:
        """Whether this sample is eligible for future automatic assembly."""

        return self.pairing_status is PairingStatus.CLEAR_PAIR


_ORIENTATION_SUFFIX = re.compile(
    r"^(?P<sample>.+?)[_. -]+(?P<orientation>forward|reverse|f|r)$",
    re.IGNORECASE,
)


def parse_read_filename(filename: str) -> tuple[str, ReadOrientation]:
    """Return a sample identifier and conservative orientation inference.

    Supported explicit suffixes are ``_F``, ``_R``, ``_Forward``, and
    ``_Reverse``; ``-``, ``.``, and spaces may replace ``_``.  Other names are
    treated as an un-oriented single-read candidate rather than guessed.
    """

    stem = Path(filename).stem
    match = _ORIENTATION_SUFFIX.match(stem)

    if match is None:
        return stem, ReadOrientation.UNSPECIFIED

    sample_id = match.group("sample")
    orientation_text = match.group("orientation").casefold()

    if orientation_text in {"f", "forward"}:
        return sample_id, ReadOrientation.FORWARD

    return sample_id, ReadOrientation.REVERSE


def classify_reads_by_filename(reads: Iterable[SangerRead]) -> list[Sample]:
    """Classify loaded reads into clear pairs, single reads, or ambiguities.

    This function only classifies.  It does not run assembly, modify reads,
    inspect sequence content, or infer a missing reverse read.  Grouping is
    case-insensitive while the first observed filename spelling is retained as
    the displayed ``sample_id``.
    """

    groups: dict[str, dict[str, object]] = {}

    for read in reads:
        sample_id, orientation = parse_read_filename(read.filename)
        group_key = sample_id.casefold()

        if group_key not in groups:
            groups[group_key] = {
                "sample_id": sample_id,
                "forward": [],
                "reverse": [],
                "unspecified": [],
            }

        group = groups[group_key]
        bucket = group[orientation.value.casefold()]
        if not any(existing is read for existing in bucket):
            bucket.append(read)

    samples = []

    for group in groups.values():
        forward_reads = tuple(group["forward"])
        reverse_reads = tuple(group["reverse"])
        unspecified_reads = tuple(group["unspecified"])

        samples.append(
            _build_sample(
                sample_id=group["sample_id"],
                forward_reads=forward_reads,
                reverse_reads=reverse_reads,
                unspecified_reads=unspecified_reads,
            )
        )

    return sorted(samples, key=lambda sample: sample.sample_id.casefold())


def _build_sample(
    sample_id: str,
    forward_reads: tuple[SangerRead, ...],
    reverse_reads: tuple[SangerRead, ...],
    unspecified_reads: tuple[SangerRead, ...],
) -> Sample:
    """Create one conservative classification result for a filename group."""

    if (
        len(forward_reads) == 1
        and len(reverse_reads) == 1
        and not unspecified_reads
    ):
        return Sample(
            sample_id=sample_id,
            classification=SampleClassification.PAIR,
            pairing_status=PairingStatus.CLEAR_PAIR,
            forward_read=forward_reads[0],
            reverse_read=reverse_reads[0],
            forward_candidates=forward_reads,
            reverse_candidates=reverse_reads,
        )

    if len(forward_reads) == 1 and not reverse_reads and not unspecified_reads:
        return Sample(
            sample_id=sample_id,
            classification=SampleClassification.SINGLE,
            pairing_status=PairingStatus.ORPHAN_FORWARD,
            forward_read=forward_reads[0],
            forward_candidates=forward_reads,
        )

    if not forward_reads and not reverse_reads and len(unspecified_reads) == 1:
        return Sample(
            sample_id=sample_id,
            classification=SampleClassification.SINGLE,
            pairing_status=PairingStatus.SINGLE_UNSPECIFIED,
            unspecified_reads=unspecified_reads,
            unspecified_candidates=unspecified_reads,
        )

    if not forward_reads and len(reverse_reads) == 1 and not unspecified_reads:
        return Sample(
            sample_id=sample_id,
            classification=SampleClassification.SINGLE,
            pairing_status=PairingStatus.ORPHAN_REVERSE,
            reverse_read=reverse_reads[0],
            reverse_candidates=reverse_reads,
            reasons=("Reverse read has no matching Forward read.",),
        )

    reasons = []

    if len(forward_reads) > 1:
        reasons.append("Multiple Forward reads share the same sample identifier.")

    if len(reverse_reads) > 1:
        reasons.append("Multiple Reverse reads share the same sample identifier.")

    if unspecified_reads and (forward_reads or reverse_reads):
        reasons.append("Oriented and un-oriented filenames share the same sample identifier.")

    if len(unspecified_reads) > 1:
        reasons.append("Multiple un-oriented reads share the same sample identifier.")

    if not reasons:
        reasons.append("Filename grouping could not determine a safe classification.")

    return Sample(
        sample_id=sample_id,
        classification=SampleClassification.AMBIGUOUS,
        pairing_status=PairingStatus.AMBIGUOUS,
        forward_read=forward_reads[0] if len(forward_reads) == 1 else None,
        reverse_read=reverse_reads[0] if len(reverse_reads) == 1 else None,
        unspecified_reads=unspecified_reads,
        forward_candidates=forward_reads,
        reverse_candidates=reverse_reads,
        unspecified_candidates=unspecified_reads,
        reasons=tuple(reasons),
    )


def _unique_reads(reads: Iterable[SangerRead]) -> tuple[SangerRead, ...]:
    """Return one stable entry per input object identity."""

    unique: list[SangerRead] = []
    for read in reads:
        if not isinstance(read, SangerRead):
            raise ValueError("sample candidates must contain SangerRead values")
        if not any(existing is read for existing in unique):
            unique.append(read)
    return tuple(unique)

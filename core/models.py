from dataclasses import dataclass, field


@dataclass
class SangerRead:
    """Container for a single Sanger sequencing read."""

    filename: str

    sequence: str

    quality: list[int]

    traces: dict[str, list[int]]

    base_positions: list[int]

    trimmed_sequence: str = ""

    trim_start: int = 0

    trim_end: int = 0

    average_quality: float = 0.0

    blast_result: dict = field(default_factory=dict)

    notes: str = ""

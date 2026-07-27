from dataclasses import dataclass, field


@dataclass
class SangerRead:
    """
    Data container for a Sanger sequencing read.
    """

    # =====================
    # Basic information
    # =====================

    filename: str

    sequence: str

    quality: list

    traces: dict

    base_positions: list


    # =====================
    # Quality statistics
    # =====================

    average_quality: float = 0.0

    q20_rate: float = 0.0

    q30_rate: float = 0.0

    hq_percent: float = 0.0


    # =====================
    # Trimming information
    # =====================

    trim_start: int = 0

    trim_end: int = 0

    trimmed_sequence: str = ""

    trimmed_quality: list = field(
        default_factory=list
    )

    trimmed_base_positions: list = field(
        default_factory=list
    )

    trimmed_traces: dict = field(
        default_factory=dict
    )


    # =====================
    # Optional flags
    # =====================

    selected: bool = True
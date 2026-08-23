"""Classification of external Finder drops for existing Studio import flows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable


AB1_SUFFIXES = frozenset({".ab1", ".abi"})
SEQUENCE_FILE_SUFFIXES = frozenset({".fas", ".fasta", ".fa", ".fna"})


class ExternalDropKind(str, Enum):
    """One unambiguous existing import route."""

    AB1_FOLDER = "AB1_FOLDER"
    AB1_FILES = "AB1_FILES"
    SEQUENCE_FILE = "SEQUENCE_FILE"
    PROJECT_BUNDLE = "PROJECT_BUNDLE"


@dataclass(frozen=True)
class ExternalDropRequest:
    """Classified paths ready for a MainWindow-to-controller handoff."""

    kind: ExternalDropKind
    paths: tuple[Path, ...]


class ExternalDropError(ValueError):
    """A clear reason an external drop must not start an import."""


def classify_external_drop_paths(paths: Iterable[str | Path]) -> ExternalDropRequest:
    """Accept only one unambiguous, already-supported import kind.

    This function intentionally does not parse files, copy AB1 data, or create
    datasets.  It only routes a Finder drop to an existing Studio workflow.
    """

    dropped = tuple(Path(path) for path in paths)
    if not dropped:
        raise ExternalDropError("Drop a supported AB1 folder, AB1 file, sequence file, or Project bundle.")
    if any(not path.exists() for path in dropped):
        missing = next(path for path in dropped if not path.exists())
        raise ExternalDropError(f"The dropped item is no longer available: {missing.name}")

    if len(dropped) == 1 and dropped[0].is_dir():
        try:
            has_ab1 = any(
                child.is_file() and child.suffix.lower() in AB1_SUFFIXES
                for child in dropped[0].iterdir()
            )
        except OSError as error:
            raise ExternalDropError(f"Could not inspect dropped folder: {dropped[0].name}") from error
        if not has_ab1:
            raise ExternalDropError("The dropped folder does not contain AB1 files.")
        return ExternalDropRequest(ExternalDropKind.AB1_FOLDER, dropped)

    if any(path.is_dir() for path in dropped):
        raise ExternalDropError("Drop one AB1 folder, or a set of AB1 files. Do not mix folders and files.")
    if any(not path.is_file() for path in dropped):
        raise ExternalDropError("Dropped items must be local files or one AB1 folder.")

    suffixes = {path.suffix.lower() for path in dropped}
    if suffixes <= AB1_SUFFIXES:
        return ExternalDropRequest(ExternalDropKind.AB1_FILES, dropped)
    if len(dropped) == 1 and suffixes == {".sangerflow"}:
        return ExternalDropRequest(ExternalDropKind.PROJECT_BUNDLE, dropped)
    if len(dropped) == 1 and suffixes <= SEQUENCE_FILE_SUFFIXES:
        return ExternalDropRequest(ExternalDropKind.SEQUENCE_FILE, dropped)

    if len(suffixes) > 1:
        raise ExternalDropError(
            "Mixed file types cannot be imported together. Drop only AB1 files, one sequence file, or one Project bundle."
        )
    suffix = next(iter(suffixes), "no extension")
    raise ExternalDropError(
        f"Unsupported file type: {suffix}. Supported items are AB1 folders, AB1 files, FASTA files, and .sangerflow bundles."
    )

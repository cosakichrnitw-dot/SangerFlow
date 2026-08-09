"""Portable zip bundles for Project descriptions and optional result payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from types import MappingProxyType
from typing import Mapping
import zipfile

from core.project import Project
from core.result_repository import FilesystemResultRepository, ResultRepository
from persistence.project_json import ProjectPersistenceError, load_project, save_project


PROJECT_BUNDLE_SCHEMA_VERSION = 1
SANGERFLOW_VERSION = "development"


class ProjectBundleError(ValueError):
    """Raised when a portable Project bundle cannot be saved or restored."""


@dataclass(frozen=True)
class ProjectBundleOptions:
    """Immutable options for the portable bundle's intentionally limited scope."""

    include_results: bool = True
    include_raw_data: bool = False


@dataclass
class LoadedProjectBundle:
    """A loaded Project plus a filesystem Repository extracted from its bundle.

    Call :meth:`cleanup` after any use of the extracted result repository.  The
    Project remains immutable; only the temporary unpacked files are removed.
    """

    project: Project
    repository: FilesystemResultRepository
    metadata: Mapping[str, object]
    extraction_directory: Path
    _temporary_directory: TemporaryDirectory

    def cleanup(self) -> None:
        """Remove the temporary extraction directory and its copied payloads."""
        self._temporary_directory.cleanup()


def save_project_bundle(
    project: Project,
    filepath: str | Path,
    repository: ResultRepository | None = None,
    options: ProjectBundleOptions | Mapping[str, object] | None = None,
) -> None:
    """Save a Project and optional FilesystemResultRepository in one zip file."""
    if not isinstance(project, Project):
        raise ProjectBundleError("project must be a Project")
    output_path = _validate_output_path(filepath)
    resolved_options = _coerce_options(options)
    if repository is not None and not isinstance(repository, FilesystemResultRepository):
        raise ProjectBundleError(
            "bundle result payloads currently require a FilesystemResultRepository"
        )

    with TemporaryDirectory(prefix="sangerflow-bundle-") as directory:
        staging = Path(directory)
        try:
            save_project(project, staging / "project.json")
        except ProjectPersistenceError as error:
            raise ProjectBundleError(str(error)) from error
        _write_json(
            staging / "bundle.json",
            {
                "schema_version": PROJECT_BUNDLE_SCHEMA_VERSION,
                "sangerflow_version": SANGERFLOW_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "include_results": resolved_options.include_results,
                "include_raw_data": resolved_options.include_raw_data,
            },
        )
        _write_json(
            staging / "datasets" / "manifest.json",
            {
                "dataset_ids": list(project.dataset_ids),
                "lineage": {
                    dataset_id: list(project.lineage(dataset_id))
                    for dataset_id in project.dataset_ids
                },
            },
        )
        _write_json(
            staging / "metadata" / "manifest.json",
            {"project_metadata_keys": sorted(project.metadata.keys())},
        )
        _stage_results(staging, repository, resolved_options.include_results)
        _write_zip(staging, output_path)


def load_project_bundle(filepath: str | Path) -> LoadedProjectBundle:
    """Load a valid ``.sangerflow`` zip into a Project and extracted repository."""
    bundle_path = _validate_input_path(filepath)
    temporary_directory = TemporaryDirectory(prefix="sangerflow-bundle-load-")
    extraction = Path(temporary_directory.name)
    try:
        with zipfile.ZipFile(bundle_path, "r") as archive:
            _validate_archive_members(archive)
            if "bundle.json" not in archive.namelist():
                raise ProjectBundleError("bundle is missing bundle.json")
            if "project.json" not in archive.namelist():
                raise ProjectBundleError("bundle is missing project.json")
            bundle_metadata = _read_bundle_metadata(archive)
            archive.extractall(extraction)
        try:
            project = load_project(extraction / "project.json")
        except ProjectPersistenceError as error:
            raise ProjectBundleError(str(error)) from error
        return LoadedProjectBundle(
            project=project,
            repository=FilesystemResultRepository(extraction),
            metadata=MappingProxyType(bundle_metadata),
            extraction_directory=extraction,
            _temporary_directory=temporary_directory,
        )
    except zipfile.BadZipFile as error:
        temporary_directory.cleanup()
        raise ProjectBundleError(f"corrupt project bundle: {error}") from error
    except Exception:
        temporary_directory.cleanup()
        raise


def _stage_results(
    staging: Path,
    repository: FilesystemResultRepository | None,
    include_results: bool,
) -> None:
    destination = staging / "results"
    destination.mkdir(parents=True, exist_ok=True)
    if include_results and repository is not None and repository.results_directory.exists():
        for source in repository.results_directory.iterdir():
            if source.is_file():
                shutil.copy2(source, destination / source.name)
    if not (destination / "index.json").exists():
        _write_json(destination / "index.json", {"results": {}})


def _write_zip(staging: Path, output_path: Path) -> None:
    try:
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for source in sorted(staging.rglob("*")):
                if source.is_file():
                    archive.write(source, source.relative_to(staging).as_posix())
    except (OSError, zipfile.BadZipFile) as error:
        raise ProjectBundleError(f"could not write project bundle: {error}") from error


def _read_bundle_metadata(archive: zipfile.ZipFile) -> dict[str, object]:
    try:
        metadata = json.loads(archive.read("bundle.json").decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProjectBundleError(f"invalid bundle.json: {error}") from error
    if not isinstance(metadata, dict):
        raise ProjectBundleError("bundle.json must be an object")
    if metadata.get("schema_version") != PROJECT_BUNDLE_SCHEMA_VERSION:
        raise ProjectBundleError(
            "unsupported bundle schema_version: "
            f"{metadata.get('schema_version')!r}; expected {PROJECT_BUNDLE_SCHEMA_VERSION}"
        )
    for key in ("sangerflow_version", "created_at"):
        if not isinstance(metadata.get(key), str) or not metadata[key]:
            raise ProjectBundleError(f"bundle.json requires {key}")
    return metadata


def _validate_archive_members(archive: zipfile.ZipFile) -> None:
    try:
        bad_member = archive.testzip()
    except zipfile.BadZipFile as error:
        raise ProjectBundleError(f"corrupt project bundle: {error}") from error
    if bad_member is not None:
        raise ProjectBundleError(f"corrupt project bundle member: {bad_member}")
    for member in archive.namelist():
        member_path = Path(member)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise ProjectBundleError("bundle contains an unsafe archive path")


def _coerce_options(
    options: ProjectBundleOptions | Mapping[str, object] | None,
) -> ProjectBundleOptions:
    if options is None:
        return ProjectBundleOptions()
    if isinstance(options, ProjectBundleOptions):
        return options
    if isinstance(options, Mapping):
        try:
            include_results = options.get("include_results", True)
            include_raw_data = options.get("include_raw_data", False)
            if not isinstance(include_results, bool) or not isinstance(include_raw_data, bool):
                raise ValueError
            return ProjectBundleOptions(
                include_results=include_results,
                include_raw_data=include_raw_data,
            )
        except ValueError as error:
            raise ProjectBundleError("bundle options must use boolean include flags") from error
    raise ProjectBundleError("options must be ProjectBundleOptions, a mapping, or None")


def _validate_output_path(filepath: str | Path) -> Path:
    if not isinstance(filepath, (str, Path)):
        raise ProjectBundleError("filepath must be a path string or Path")
    path = Path(filepath)
    if not path.name or path.exists() and path.is_dir():
        raise ProjectBundleError("filepath must refer to a file")
    if not path.parent.is_dir():
        raise ProjectBundleError("filepath parent directory does not exist")
    return path


def _validate_input_path(filepath: str | Path) -> Path:
    if not isinstance(filepath, (str, Path)):
        raise ProjectBundleError("filepath must be a path string or Path")
    path = Path(filepath)
    if not path.is_file():
        raise ProjectBundleError(f"project bundle does not exist: {path}")
    return path


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
    except (OSError, TypeError, ValueError) as error:
        raise ProjectBundleError(f"could not write bundle metadata: {error}") from error

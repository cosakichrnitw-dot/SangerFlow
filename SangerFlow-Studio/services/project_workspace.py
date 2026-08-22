"""Filesystem conveniences layered beside, not inside, a Project bundle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


class WorkspaceError(ValueError):
    """Raised when a Studio workspace cannot be created or used safely."""


@dataclass(frozen=True)
class ProjectWorkspace:
    """Conventional folders next to one logical ``.sangerflow`` bundle."""

    root: Path
    bundle_path: Path

    @property
    def raw_data_directory(self) -> Path:
        return self.root / "Raw_Data"

    @property
    def exports_directory(self) -> Path:
        return self.root / "Exports"

    @property
    def metadata_directory(self) -> Path:
        return self.root / "Metadata"

    @property
    def reports_directory(self) -> Path:
        return self.root / "Reports"

    def ensure_directories(self) -> None:
        for directory in (
            self.root,
            self.raw_data_directory,
            self.exports_directory,
            self.metadata_directory,
            self.reports_directory,
        ):
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise WorkspaceError(f"could not create workspace directory: {directory}: {error}") from error


def create_project_workspace(location: str | Path, project_name: str) -> ProjectWorkspace:
    """Create the conventional workspace directories without touching Project models."""

    location_path = Path(location).expanduser()
    if not project_name or not project_name.strip():
        raise WorkspaceError("project name is required")
    root = location_path / filesystem_safe_name(project_name)
    if root.exists():
        raise WorkspaceError(f"project workspace already exists: {root}")
    workspace = ProjectWorkspace(
        root=root,
        bundle_path=root / f"{filesystem_safe_name(project_name)}.sangerflow",
    )
    workspace.ensure_directories()
    return workspace


def workspace_for_bundle(bundle_path: str | Path | None) -> ProjectWorkspace | None:
    """Resolve an optional workspace from the current Bundle's parent directory."""

    if not bundle_path:
        return None
    path = Path(bundle_path).expanduser()
    if not path.name:
        return None
    return ProjectWorkspace(root=path.parent, bundle_path=path)


def filesystem_safe_name(value: str) -> str:
    """Return a portable, readable filename component without changing Project names."""

    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._")
    return safe or "SangerFlow_Project"

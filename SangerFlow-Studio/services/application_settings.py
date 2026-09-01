"""Machine-local Studio preferences, intentionally separate from Projects."""

from __future__ import annotations

from PySide6.QtCore import QSettings

from core.tool_manager import ToolStatus
from tools.mafft_tool import ToolInfo, detect_mafft, resolve_mafft_executable


ORGANIZATION_NAME = "SangerFlow"
APPLICATION_NAME = "SangerFlow-Studio"
MAFFT_EXECUTABLE_KEY = "tools/mafft/executable_path"


def studio_settings() -> QSettings:
    """Return the platform-native per-user settings store for Studio."""

    return QSettings(ORGANIZATION_NAME, APPLICATION_NAME)


def configured_mafft_executable(settings: QSettings | None = None) -> str | None:
    value = (settings or studio_settings()).value(MAFFT_EXECUTABLE_KEY, "")
    text = str(value).strip() if value is not None else ""
    return text or None


def set_configured_mafft_executable(
    executable_path: str | None,
    settings: QSettings | None = None,
) -> None:
    store = settings or studio_settings()
    text = str(executable_path).strip() if executable_path is not None else ""
    if text:
        store.setValue(MAFFT_EXECUTABLE_KEY, text)
    else:
        store.remove(MAFFT_EXECUTABLE_KEY)
    store.sync()


def resolve_studio_mafft_executable(settings: QSettings | None = None) -> str:
    """Resolve MAFFT from the current machine preference or native PATH."""

    return resolve_mafft_executable(configured_mafft_executable(settings))


def studio_mafft_info(settings: QSettings | None = None) -> ToolInfo:
    """Probe the configured MAFFT path or native PATH for display in Studio."""

    return detect_mafft(configured_mafft_executable(settings) or "mafft")


def mafft_info_for_executable_path(
    executable_path: str | None,
    *,
    settings: QSettings | None = None,
) -> ToolInfo:
    """Probe one candidate path, or the normal automatic-detection route.

    This is deliberately a version probe only; it never runs an alignment or
    mutates Project data.  Keeping it here lets Tool Settings and the setup
    dialogs use the same validation policy and machine-local persistence.
    """

    path = str(executable_path).strip() if executable_path is not None else ""
    return detect_mafft(path) if path else studio_mafft_info(settings)


def store_validated_mafft_executable(
    executable_path: str,
    settings: QSettings | None = None,
) -> ToolInfo:
    """Persist *executable_path* only after MAFFT's version probe succeeds."""

    info = mafft_info_for_executable_path(executable_path, settings=settings)
    if info.status is ToolStatus.AVAILABLE:
        set_configured_mafft_executable(info.executable_path, settings)
    return info

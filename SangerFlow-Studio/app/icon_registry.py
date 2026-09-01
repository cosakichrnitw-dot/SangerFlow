"""Central, replaceable icon resolution for Studio presentation actions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from core.resource_paths import application_resource_path


_ACTION_ICON_NAMES: dict[str, str] = {
    "dataset.open_chromatogram_viewer": "chromatogram",
    "dataset.edit_sequences": "sequence_editor",
    "dataset.align_sequences": "align",
    "dataset.open_alignment_viewer": "sequence_editor",
    "dataset.import_sample_metadata": "metadata",
    "dataset.create_metadata_template": "metadata",
    "dataset.rename_dataset": "rename",
    "dataset.remove_dataset": "delete",
    "dataset.create_selection_dataset": "create_dataset",
    "dataset.rename_record": "rename",
    "dataset.batch_rename_records": "rename",
    "dataset.run_blast": "blast",
    "dataset.import_blast_xml": "import",
    "dataset.open_quality_report": "quality_report",
    "chromatogram.toggle_trim_region": "show_trim_region",
    "chromatogram.open_sequence_editor": "sequence_editor",
    "chromatogram.build_consensus": "consensus",
    "chromatogram.open_quality_report": "quality_report",
    "chromatogram.align": "align",
    "alignment.review_chromatograms": "chromatogram",
    "alignment.run_blast": "blast",
    "alignment.export_selection_fasta": "export",
    "alignment.exclude_columns": "hide",
    "alignment.include_columns": "show",
    "alignment.delete_selected_columns": "delete",
    "alignment.hide_rows": "hide",
    "alignment.show_all_rows": "show",
    "alignment.rename_selected_row": "rename",
    "alignment.delete_selected_rows": "delete",
    "alignment.save_edited_alignment": "save",
    "sequence_editor.save": "save",
    "sequence_editor.copy": "copy",
    "sequence_editor.paste": "paste",
    "sequence_editor.rename_row": "rename",
    "sequence_editor.hide_rows": "hide",
    "sequence_editor.show_all_rows": "show",
    "sequence_editor.delete_rows": "delete",
    "sequence_editor.review_evidence": "open_source_sequence_editor",
    "sequence_editor.align": "align",
    "identification.apply_filter": "filter",
    "identification.clear_filter": "clear",
    "identification.select_all_filtered": "select",
    "identification.clear_selection": "clear",
    "identification.create_dataset": "create_dataset",
    "identification.apply_blast_metadata": "apply_metadata",
    "consensus_review.create_dataset": "create_dataset",
    "single_consensus.accept": "accept",
    "single_consensus.jump_forward": "next",
    "single_consensus.jump_reverse": "previous",
    "single_consensus.previous_conflict": "previous",
    "single_consensus.next_conflict": "next",
    "single_consensus.create_dataset": "create_dataset",
    "multiple_consensus.previous_variable_site": "previous",
    "multiple_consensus.next_variable_site": "next",
    "multiple_consensus.previous_conflict": "previous",
    "multiple_consensus.next_conflict": "next",
    "multiple_consensus.create_dataset": "create_dataset",
    "alignment_chromatogram.toggle_trim_region": "show_trim_region",
    "alignment_chromatogram.open_quality_report": "quality_report",
}


def studio_icon(name: str, *, fallback_size: int = 32) -> QIcon:
    """Load a replaceable PNG or SVG without relying on Studio's working directory.

    Designer-provided PNG assets are preferred when present. Existing SVGs
    remain the fallback for all other presentation actions and for a missing
    PNG asset. QIcon performs normal platform/high-DPI scaling.
    """

    resources = application_resource_path("SangerFlow-Studio", "resources", "icons")
    png_path = resources / f"{name}.png"
    if png_path.is_file():
        icon = QIcon(str(png_path))
        if not icon.isNull():
            return icon

    path = resources / f"{name}.svg"
    if not path.is_file():
        return QIcon()
    icon = QIcon(str(path))
    if not icon.isNull():
        return icon
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return QIcon()
    pixmap = QPixmap(fallback_size, fallback_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def action_icon(action_id: str) -> QIcon:
    """Return the semantic icon for a ViewerAction, or an empty icon."""

    icon_name = _ACTION_ICON_NAMES.get(action_id)
    if icon_name is None:
        if ".export" in action_id or "export_" in action_id:
            icon_name = "export"
        elif action_id.endswith(".undo"):
            icon_name = "undo"
        elif action_id.endswith(".redo"):
            icon_name = "redo"
        elif action_id.endswith(".copy_selection"):
            icon_name = "copy"
        elif action_id.endswith(".paste"):
            icon_name = "paste"
    return studio_icon(icon_name) if icon_name else QIcon()

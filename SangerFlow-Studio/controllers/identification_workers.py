"""Qt worker objects for Studio identification services."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from core.blast_result import BlastAnalysisMode, BlastResultDataset
from core.sequence_dataset import SequenceDataset
from workflow.ncbi_blast_service import NcbiBlastProgress, NcbiBlastRunner, NcbiBlastSettings


class BlastWorker(QObject):
    """Run NCBI BLAST off the Qt main thread."""

    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        dataset: SequenceDataset,
        settings: NcbiBlastSettings,
        *,
        analysis_mode: BlastAnalysisMode = BlastAnalysisMode.IDENTIFICATION,
    ) -> None:
        super().__init__()
        self._dataset = dataset
        self._settings = settings
        self._analysis_mode = analysis_mode
        self._cancelled = False

    @Slot()
    def run(self) -> None:
        try:
            runner = NcbiBlastRunner(self._settings)
            result = runner.run_dataset(
                self._dataset,
                analysis_mode=self._analysis_mode,
                progress=self._emit_progress,
                should_cancel=self._should_cancel,
            )
        except Exception as error:
            self.failed.emit(str(error))
        else:
            self.completed.emit(result)
        finally:
            self.finished.emit()

    @Slot()
    def cancel(self) -> None:
        self._cancelled = True

    def _emit_progress(self, progress: NcbiBlastProgress) -> None:
        self.progress.emit(progress)

    def _should_cancel(self) -> bool:
        thread = self.thread()
        return self._cancelled or (thread is not None and thread.isInterruptionRequested())

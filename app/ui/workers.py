"""QThread wrappers so the GUI never blocks."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal


class BackgroundWorker(QObject):
    """Runs a callable in a QThread and emits the result/error."""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)


def run_in_thread(
    parent: QObject, fn: Callable[[], object]
) -> tuple[QThread, BackgroundWorker]:
    """Start a worker in a new thread tied to `parent`'s lifetime."""
    thread = QThread(parent)
    worker = BackgroundWorker(fn)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread, worker

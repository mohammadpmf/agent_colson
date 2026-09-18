"""QThread wrappers so the GUI never blocks."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot


class _Callbacks(QObject):
    def __init__(self, parent, on_done, on_failed):
        super().__init__(parent)
        self.on_done = on_done
        self.on_failed = on_failed

    @Slot(object)
    def done(self, result):
        if self.on_done:
            self.on_done(result)

    @Slot(str)
    def failed(self, error):
        if self.on_failed:
            self.on_failed(error)


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
    parent: QObject, fn: Callable[[], object], on_done=None, on_failed=None
) -> tuple[QThread, BackgroundWorker]:
    """Start a worker in a new thread tied to `parent`'s lifetime."""
    thread = QThread(parent)
    worker = BackgroundWorker(fn)
    callbacks = _Callbacks(parent, on_done, on_failed)
    thread._worker = worker
    thread._callbacks = callbacks
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(callbacks.done)
    worker.failed.connect(callbacks.failed)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(callbacks.deleteLater)
    thread.start()
    return thread, worker

import threading

import pytest

from briochette.core import QThread, QTimer, pyqtSignal


def test_single_shot_runs_after_the_delay(qtbot):
    got = []
    QTimer.singleShot(10, lambda: got.append(1))
    assert got == []
    qtbot.waitUntil(lambda: got == [1], timeout=1000)


def test_repeating_timer_until_stopped(qtbot):
    timer, ticks = QTimer(), []
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(5)
    assert timer.isActive() and timer.interval() == 5
    qtbot.waitUntil(lambda: len(ticks) >= 3, timeout=1000)
    timer.stop()
    count = len(ticks)
    qtbot.wait(30)
    assert len(ticks) == count and not timer.isActive()


def test_single_shot_timer_object(qtbot):
    timer = QTimer()
    timer.setSingleShot(True)
    with qtbot.waitSignal(timer.timeout, timeout=1000):
        timer.start(5)
    assert not timer.isActive()


def test_wait_signal_times_out(qtbot):
    timer = QTimer()
    with pytest.raises(TimeoutError):
        with qtbot.waitSignal(timer.timeout, timeout=50):
            pass


class Worker(QThread):
    progress = pyqtSignal(int)

    def run(self):
        for i in range(3):
            self.progress.emit(i)


def test_thread_signals_are_delivered_on_the_gui_thread(qtbot):
    worker, got = Worker(), []
    worker.progress.connect(lambda i: got.append((i, threading.get_ident())))
    with qtbot.waitSignal(worker.finished, timeout=2000):
        worker.start()
    worker.wait()
    assert got == [(i, threading.get_ident()) for i in range(3)]
    assert not worker.isRunning()

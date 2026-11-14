"""The opt-in hook: PyQt6 imports resolve to briochette, at runtime only."""

import sys

import pytest

from briochette import compat, core, gui, widgets


@pytest.fixture
def hook():
    compat.install()
    yield
    compat.uninstall()
    for name in [n for n in sys.modules if n == "PyQt6" or n.startswith("PyQt6.")]:
        del sys.modules[name]


def test_without_the_hook_pyqt6_is_not_ours():
    assert "PyQt6" not in sys.modules or sys.modules["PyQt6"].__name__ != "briochette"
    try:
        import PyQt6.QtWidgets as real  # noqa: F401
    except ImportError:
        return
    assert real is not widgets


def test_modules_map_to_briochette(hook):
    from PyQt6 import QtCore, QtGui, QtWidgets

    assert (QtCore, QtGui, QtWidgets) == (core, gui, widgets)
    from PyQt6.QtWidgets import QApplication

    assert QApplication is widgets.QApplication


def test_slots_and_properties(hook):
    from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

    class Thing(QObject):
        changed = pyqtSignal(int)

        def __init__(self):
            super().__init__()
            self._n = 0

        @pyqtProperty(int)
        def n(self):
            return self._n

        @n.setter
        def n(self, value):
            self._n = value
            self.changed.emit(value)

        @pyqtSlot(int)
        def double(self, value):
            return value * 2

    thing, got = Thing(), []
    thing.changed.connect(got.append)
    thing.n = 3
    assert (thing.n, got, thing.double(2)) == (3, [3], 4)


def test_unknown_pyqt6_module_says_so(hook):
    with pytest.raises(ImportError, match="QtWebEngineWidgets"):
        import PyQt6.QtWebEngineWidgets  # noqa: F401


PLAN_COUNTER = """
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtGui import QShortcut, QKeySequence

class Counter(QWidget):
    def __init__(self):
        super().__init__()
        self.count = 0
        self.label = QLabel("Count: 0")
        self.increment = QPushButton("+")
        self.increment.setAccessibleName("Increment")
        self.increment.clicked.connect(self.inc)
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addWidget(self.increment)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.reset)

    def inc(self):
        self.count += 1
        self.label.setText(f"Count: {self.count}")

    def reset(self):
        self.count = 0
        self.label.setText("Count: 0")
"""


def test_the_plans_pyqt6_counter_runs_unchanged(hook, qtbot):
    from PyQt6.QtCore import Qt

    namespace = {}
    exec(PLAN_COUNTER, namespace)
    window = namespace["Counter"]()
    qtbot.addWidget(window)
    qtbot.mouseClick(window.increment, Qt.MouseButton.LeftButton)
    assert window.label.text() == "Count: 1"
    qtbot.keyClick(window, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
    assert window.label.text() == "Count: 0"

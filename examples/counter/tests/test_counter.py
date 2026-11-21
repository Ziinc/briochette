from briochette.core import Qt
from counter.app import Counter


def test_increments(qtbot):
    window = Counter()
    qtbot.addWidget(window)
    qtbot.mouseClick(window.increment, Qt.MouseButton.LeftButton)
    assert window.label.text() == "Count: 1"


def test_ctrl_r_resets(qtbot):
    window = Counter()
    qtbot.addWidget(window)
    qtbot.mouseClick(window.increment, Qt.MouseButton.LeftButton)
    qtbot.keyClick(window, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
    assert window.label.text() == "Count: 0"

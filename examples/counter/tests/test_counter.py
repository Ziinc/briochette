from briochette.core import Qt
from counter.app import Counter


def test_increments(qtbot):
    window = Counter()
    qtbot.addWidget(window)
    qtbot.mouseClick(window.increment, Qt.MouseButton.LeftButton)
    assert window.label.text() == "Count: 1"

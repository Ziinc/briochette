"""Every platform call briochette makes is one levain's calls.json defines,
with arguments it knows."""

import json
from pathlib import Path

from briochette.gui import QKeySequence
from briochette.widgets import QApplication, QLabel, QMenuBar, QWidget

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "calls.json").read_text())
VALID = [c["json"] for c in FIXTURES if "json" in c and "reply" not in c]
KNOWN = {}
for call in VALID:
    KNOWN.setdefault(call["call"], set()).update(call["args"])


def test_calls_briochette_makes_are_in_levains_vocabulary(qtbot, qapp):
    start = len(qtbot.host.calls)
    first = QWidget()
    qtbot.addWidget(first)
    second = QLabel("two")
    second.setWindowTitle("Details")
    second.show()
    second.setWindowTitle("Details (1)")
    second.close()
    QApplication.clipboard().setText("x")
    QApplication.clipboard().text()
    bar = QMenuBar()
    bar.addMenu("File").addAction("Open").setShortcut(QKeySequence("Ctrl+O"))
    qtbot.wait(0)
    qapp._call("app.exit", {"code": 0})

    made = qtbot.host.calls[start:]
    assert {c["call"] for c in made} >= {
        "window.open",
        "window.set_title",
        "window.close",
        "clipboard.write",
        "clipboard.read",
        "menu.set",
        "app.exit",
    }
    for call in made:
        assert set(call) == {"call", "ref", "args"}
        assert isinstance(call["ref"], int)
        assert call["call"] in KNOWN, call
        assert set(call["args"]) <= KNOWN[call["call"]], call


def test_headless_host_refuses_unknown_calls_as_levain_does(qtbot):
    unknown = next(c for c in FIXTURES if c["name"] == "unknown call")
    replies = []
    host = qtbot.host
    handler, host._handler = host._handler, lambda event: replies.append(json.loads(event))
    try:
        host.call(unknown["json"])
    finally:
        host._handler = handler
    assert replies == [unknown["reply"]]

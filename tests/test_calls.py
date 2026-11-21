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


def test_desktop_calls_are_in_levains_vocabulary(qtbot):
    from briochette.core import QStandardPaths, Qt, QUrl
    from briochette.gui import QDesktopServices, QIcon
    from briochette.widgets import QFileDialog, QMenu, QMessageBox, QSystemTrayIcon

    start = len(qtbot.host.calls)
    w = QWidget()
    qtbot.addWidget(w)
    w.showMaximized()
    w.showMinimized()
    w.showNormal()
    w.showFullScreen()
    w.activateWindow()
    w.setMinimumSize(10, 10)
    w.resize(100, 100)
    w.move(1, 2)
    w.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    QMessageBox.information(w, "t", "m")
    QMessageBox.question(w, "t", "m")
    QFileDialog.getOpenFileName(w, "t", "/home", "Images (*.png)")
    QFileDialog.getOpenFileNames(w, "t")
    QFileDialog.getExistingDirectory(w, "t", "/home")
    QFileDialog.getSaveFileName(w, "t", "/home/a.csv", "CSV (*.csv)")
    QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    QDesktopServices.openUrl(QUrl("https://example.com"))
    menu = QMenu(w)
    menu.addAction("Copy")
    menu.exec()
    tray = QSystemTrayIcon(QIcon("/tmp/i.png"))
    tray.setToolTip("t")
    tray.setContextMenu(menu)
    tray.show()
    tray.showMessage("t", "m")
    tray.hide()

    made = qtbot.host.calls[start:]
    for call in made:
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

"""Dialogs, paths, window events and state, the tray and images: the host's
platform calls and window events behind Qt's API."""

import pytest

from briochette.core import QPoint, QSize, QStandardPaths, Qt, QUrl
from briochette.gui import QDesktopServices, QIcon, QPixmap
from briochette.widgets import (
    QFileDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)


def window(qtbot, cls=QWidget):
    w = cls()
    QVBoxLayout(w).addWidget(QLabel("x"))
    qtbot.addWidget(w)
    return w


def calls(qtbot, name):
    return [c["args"] for c in qtbot.host.calls if c["call"] == name]


def test_message_boxes_show_native_dialogs(qtbot):
    w = window(qtbot)
    assert QMessageBox.information(w, "Saved", "All saved.") == QMessageBox.StandardButton.Ok
    QMessageBox.warning(w, "Careful", "Disk almost full.")
    QMessageBox.critical(None, "Failed", "Could not save.")
    assert calls(qtbot, "dialog.message")[-3:] == [
        {"title": "Saved", "message": "All saved.", "kind": "info"},
        {"title": "Careful", "message": "Disk almost full.", "kind": "warning"},
        {"title": "Failed", "message": "Could not save.", "kind": "error"},
    ]


def test_a_question_is_a_confirmation(qtbot):
    yes, no = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No
    qtbot.host.answer("dialog.confirm", True)
    assert QMessageBox.question(None, "Delete", "Delete 3 jobs?") == yes
    qtbot.host.answer("dialog.confirm", False)
    assert QMessageBox.question(None, "Delete", "Delete 3 jobs?") == no
    assert calls(qtbot, "dialog.confirm")[-1] == {
        "title": "Delete",
        "message": "Delete 3 jobs?",
        "kind": "info",
        "ok": "Yes",
        "cancel": "No",
    }


def test_file_dialogs_return_paths_and_the_filter(qtbot):
    qtbot.host.answer("dialog.open", "/home/ana/a.png")
    path, chosen = QFileDialog.getOpenFileName(
        None, "Open image", "/home/ana", "Images (*.png *.jpg);;All files (*)"
    )
    assert (path, chosen) == ("/home/ana/a.png", "Images (*.png *.jpg)")
    assert calls(qtbot, "dialog.open")[-1] == {
        "title": "Open image",
        "default_path": "/home/ana",
        "filters": [{"name": "Images", "extensions": ["png", "jpg"]}, {"name": "All files", "extensions": ["*"]}],
    }
    qtbot.host.answer("dialog.open", ["/a", "/b"])
    assert QFileDialog.getOpenFileNames(None, "Add") == (["/a", "/b"], "")
    assert calls(qtbot, "dialog.open")[-1]["multiple"] is True
    qtbot.host.answer("dialog.open", None)
    assert QFileDialog.getOpenFileName() == ("", "")
    qtbot.host.answer("dialog.open", "/home/ana/photos")
    assert QFileDialog.getExistingDirectory(None, "Pick") == "/home/ana/photos"
    assert calls(qtbot, "dialog.open")[-1]["directory"] is True
    qtbot.host.answer("dialog.save", "/home/ana/jobs.csv")
    assert QFileDialog.getSaveFileName(None, "Export", "jobs.csv", "CSV (*.csv)") == (
        "/home/ana/jobs.csv",
        "CSV (*.csv)",
    )
    assert calls(qtbot, "dialog.save")[-1]["default_name"] == "jobs.csv"


def test_standard_paths_come_from_the_host(qtbot):
    loc = QStandardPaths.StandardLocation
    assert QStandardPaths.writableLocation(loc.AppDataLocation) == "/data/app"
    assert QStandardPaths.writableLocation(loc.DocumentsLocation) == "/home/ana/Documents"
    assert QStandardPaths.writableLocation(loc.TempLocation) == "/tmp"
    assert QStandardPaths.writableLocation(loc.MusicLocation) == ""


def test_urls_open_in_the_system_browser(qtbot):
    assert QDesktopServices.openUrl(QUrl("https://example.com"))
    assert calls(qtbot, "app.open_url")[-1] == {"url": "https://example.com"}
    assert QUrl.fromLocalFile("/tmp/a b.txt").toString() == "file:///tmp/a%20b.txt"
    assert QUrl("file:///tmp/a%20b.txt").toLocalFile() == "/tmp/a b.txt"
    assert QUrl("file:///tmp/a%20b.txt").isLocalFile()


class Guarded(QWidget):
    def __init__(self):
        super().__init__()
        self.allow = False
        self.asked = 0

    def closeEvent(self, event):
        self.asked += 1
        if self.allow:
            event.accept()
        else:
            event.ignore()


def test_close_event_decides_whether_the_window_closes(qtbot, qapp):
    w = window(qtbot, Guarded)
    qtbot.wait(0)
    assert calls(qtbot, "window.prevent_close")[-1] == {"window": w.winId(), "on": True}
    qapp._dispatch({"type": "window", "window": w.winId(), "event": "close-requested"})
    assert w.asked == 1 and w.isVisible()
    w.allow = True
    qapp._dispatch({"type": "window", "window": w.winId(), "event": "close-requested"})
    assert not w.isVisible()


def test_a_window_closed_by_the_user_is_no_longer_shown(qtbot, qapp):
    w = window(qtbot)
    qapp._dispatch({"type": "window", "window": w.winId(), "event": "closed"})
    assert not w.isVisible()


class Sized(QWidget):
    def __init__(self):
        super().__init__()
        self.sizes, self.moves = [], []

    def resizeEvent(self, event):
        self.sizes.append((event.size(), event.oldSize()))

    def moveEvent(self, event):
        self.moves.append(event.pos())


def test_resizes_and_moves_reach_the_widget(qtbot, qapp):
    w = window(qtbot, Sized)
    qapp._dispatch({"type": "window", "window": w.winId(), "event": "resized", "width": 640.0, "height": 480.0})
    qapp._dispatch({"type": "window", "window": w.winId(), "event": "moved", "x": 20.0, "y": 10.0})
    assert w.size() == QSize(640, 480) and (w.width(), w.height()) == (640, 480)
    assert w.sizes == [(QSize(640, 480), QSize(-1, -1))]
    assert w.pos() == QPoint(20, 10) and w.moves == [QPoint(20, 10)]


def test_window_state_size_and_position_are_calls(qtbot):
    w = window(qtbot)
    win = w.winId()
    w.showMaximized()
    w.showMinimized()
    w.showNormal()
    w.showFullScreen()
    w.activateWindow()
    w.setMinimumSize(320, 240)
    w.resize(800, 600)
    w.move(10, 20)
    w.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    names = [c["call"] for c in qtbot.host.calls if c["args"].get("window") == win]
    assert names[-9:] == [
        "window.maximize",
        "window.minimize",
        "window.unmaximize",
        "window.set_fullscreen",
        "window.focus",
        "window.set_min_size",
        "window.set_bounds",
        "window.set_bounds",
        "window.set_always_on_top",
    ]
    assert calls(qtbot, "window.set_bounds")[-2:] == [
        {"window": win, "width": 800, "height": 600},
        {"window": win, "x": 10, "y": 20},
    ]


def test_dropped_files_reach_drop_event(qtbot, qapp):
    class Target(QWidget):
        def __init__(self):
            super().__init__()
            self.setAcceptDrops(True)
            self.got = []

        def dropEvent(self, event):
            self.got = [u.toLocalFile() for u in event.mimeData().urls()]
            event.acceptProposedAction()

    w = window(qtbot, Target)
    qapp._dispatch({"type": "window", "window": w.winId(), "event": "drop", "paths": ["/tmp/a.png"], "x": 1.0, "y": 2.0})
    assert w.got == ["/tmp/a.png"]


def test_a_pixmap_label_is_an_image(qtbot):
    w = QWidget()
    label = QLabel()
    QVBoxLayout(w).addWidget(label)
    qtbot.addWidget(w)
    label.setPixmap(QPixmap("/tmp/logo.png"))
    qtbot.wait(0)
    node = qtbot.host.tree(w.winId())["c"][0]
    assert node["t"] == "img" and node["a"]["src"] == "/tmp/logo.png"
    assert label.pixmap().isNull() is False and QPixmap().isNull()


def test_the_tray_icon_shows_its_menu_and_messages(qtbot, qapp):
    menu = QMenu()
    shown = []
    menu.addAction("Show", lambda: shown.append(1))
    tray = QSystemTrayIcon(QIcon("/tmp/tray.png"))
    tray.setToolTip("Jobs")
    tray.setContextMenu(menu)
    clicks = []
    tray.activated.connect(clicks.append)
    tray.show()
    assert tray.isVisible()
    spec = calls(qtbot, "tray.set")[-1]
    assert spec["icon"] == "/tmp/tray.png" and spec["tooltip"] == "Jobs"
    assert [i["label"] for i in spec["items"]] == ["Show"]
    qapp._dispatch({"type": "menu", "window": 0, "event": spec["items"][0]["id"]})
    assert shown == [1]
    qapp._dispatch({"type": "tray", "event": "click"})
    qapp._dispatch({"type": "tray", "event": "double-click"})
    reason = QSystemTrayIcon.ActivationReason
    assert clicks == [reason.Trigger, reason.DoubleClick]
    tray.showMessage("Done", "3 jobs exported")
    assert calls(qtbot, "notification.send")[-1] == {"title": "Done", "body": "3 jobs exported"}
    tray.hide()
    assert calls(qtbot, "tray.remove") and not tray.isVisible()


def test_a_context_menu_pops_up_in_its_window(qtbot):
    w = window(qtbot)
    menu = QMenu(w)
    menu.addAction("Copy")
    menu.exec()
    args = calls(qtbot, "menu.popup")[-1]
    assert args["window"] == w.winId() and [i["label"] for i in args["items"]] == ["Copy"]


def test_phones_going_to_the_background_change_the_application_state(qtbot, qapp):
    states = []
    qapp.applicationStateChanged.connect(states.append)
    qapp._dispatch({"type": "window", "window": 0, "event": "suspended"})
    qapp._dispatch({"type": "window", "window": 0, "event": "resumed"})
    s = Qt.ApplicationState
    assert states == [s.ApplicationSuspended, s.ApplicationActive]
    assert qapp.applicationState() == s.ApplicationActive


@pytest.mark.parametrize(
    "text, filters",
    [
        ("", []),
        ("*.txt", [{"name": "*.txt", "extensions": ["txt"]}]),
        ("Text (*.txt *.md);;Any (*)", [{"name": "Text", "extensions": ["txt", "md"]}, {"name": "Any", "extensions": ["*"]}]),
    ],
)
def test_name_filters_are_read_as_qt_writes_them(text, filters):
    from briochette.widgets import _filters

    assert _filters(text) == filters

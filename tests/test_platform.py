"""Clipboard, shortcuts and menus: platform calls and the frame's keymap."""

from briochette.core import Qt
from briochette.gui import QAction, QKeySequence, QShortcut
from briochette.widgets import QApplication, QLabel, QMenuBar, QVBoxLayout, QWidget


def window(qtbot):
    w = QWidget()
    QVBoxLayout(w).addWidget(QLabel("x"))
    qtbot.addWidget(w)
    return w


def test_key_sequence_in_gpui_syntax():
    assert QKeySequence("Ctrl+R").toString() == "Ctrl+R"
    assert QKeySequence("Ctrl+Shift+S")._keys() == "secondary-shift-s"
    assert QKeySequence("Alt+Return")._keys() == "alt-enter"
    assert QKeySequence("Esc")._keys() == "escape"
    assert QKeySequence("F5")._keys() == "f5"
    assert QKeySequence("Ctrl+-")._keys() == "secondary--"


def test_clipboard_round_trips_through_the_host(qtbot):
    QApplication.clipboard().setText("hi")
    assert QApplication.clipboard().text() == "hi"
    calls = [c["call"] for c in qtbot.host.calls]
    assert calls[-2:] == ["clipboard.write", "clipboard.read"]


def test_shortcut_goes_in_the_keymap_and_fires(qtbot):
    w, got = window(qtbot), []
    shortcut = QShortcut(QKeySequence("Ctrl+R"), w, activated=lambda: got.append(1))
    qtbot.wait(0)
    assert qtbot.host.keymap(w.winId()) == [{"keys": "secondary-r", "action": shortcut._id}]
    qtbot.keyClick(w, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
    assert got == [1]
    qtbot.keyClick(w, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    assert got == [1]


def test_disabled_shortcut_leaves_the_keymap(qtbot):
    w = window(qtbot)
    shortcut = QShortcut(QKeySequence("Ctrl+R"), w)
    shortcut.setEnabled(False)
    qtbot.wait(0)
    assert qtbot.host.keymap(w.winId()) == []


def test_menu_bar_sets_native_menus_and_triggers_actions(qtbot, qapp):
    bar = QMenuBar()
    file = bar.addMenu("&File")
    opened = []
    open_action = file.addAction("Open")
    open_action.setShortcut(QKeySequence("Ctrl+O"))
    open_action.triggered.connect(lambda: opened.append(1))
    file.addSeparator()
    quit_action = QAction("Quit", file)
    file.addAction(quit_action)
    qtbot.wait(0)
    assert qtbot.host.menus == [
        {
            "title": "File",
            "items": [
                {"id": open_action._id, "label": "Open", "keys": "secondary-o"},
                {"separator": True},
                {"id": quit_action._id, "label": "Quit"},
            ],
        }
    ]
    qapp._dispatch({"type": "menu", "window": 0, "event": open_action._id})
    assert opened == [1]


def test_constructor_keywords_connect_signals():
    got = []
    action = QAction("x", triggered=lambda: got.append(1))
    action.trigger()
    assert got == [1]

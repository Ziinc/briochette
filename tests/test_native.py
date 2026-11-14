"""The app against the host's C ABI, through a stand-in `_briochette` module."""

import json
import threading
import types

import pytest

from briochette import widgets
from briochette.widgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget


class FakeNative(types.ModuleType):
    """Records what the app sends; `send` delivers an event as the host's sink does."""

    def __init__(self):
        super().__init__("_briochette")
        self.renders, self.calls, self.handler = [], [], None

    def render(self, window, frame):
        self.renders.append((window, json.loads(frame)))

    def call(self, message):
        self.calls.append(json.loads(message))

    def set_event_handler(self, handler):
        self.handler = handler

    def send(self, event):
        # From another thread, as the host's UI thread does.
        t = threading.Thread(target=self.handler, args=(json.dumps(event),))
        t.start()
        t.join()


@pytest.fixture
def native(monkeypatch):
    fake = FakeNative()
    monkeypatch.setitem(__import__("sys").modules, "_briochette", fake)
    monkeypatch.setattr(QApplication, "_instance", None)
    yield fake


def counter():
    window = QWidget()
    window.label = QLabel("Count: 0")
    window.button = QPushButton("+")
    window.button.clicked.connect(lambda: window.label.setText("Count: 1"))
    layout = QVBoxLayout(window)
    layout.addWidget(window.label)
    layout.addWidget(window.button)
    return window


def test_uses_the_native_module_when_present(native):
    app = QApplication([])
    window = counter()
    window.show()
    assert native.renders == [(0, {"root": window._node()})]


def test_host_events_run_on_the_loop_and_patches_follow(native):
    app = QApplication([])
    window = counter()
    window.show()
    window.button.clicked.connect(app.quit)
    guard = threading.Timer(5, app.quit)  # never hang the suite
    guard.start()
    native.send({"type": "click", "window": 0, "event": window.button._id, "values": {}})
    try:
        assert app.exec() == 0
    finally:
        guard.cancel()
    assert native.renders[-1] == (0, {"patch": [{"op": "replace", "at": [0, 0], "node": "Count: 1"}]})


def test_resync_sends_the_window_whole(native):
    app = QApplication([])
    window = counter()
    window.show()
    app._dispatch({"type": "resync", "window": 0})
    assert native.renders[-1] == (0, {"root": window._node()})


def test_second_window_is_opened_and_closed_through_platform_calls(native):
    app = QApplication([])
    counter().show()
    second = QLabel("two")
    second.show()
    assert native.calls[0]["call"] == "window.open"
    assert native.calls[0]["args"]["window"] == 1
    second.close()
    assert native.calls[-1]["call"] == "window.close"
    assert native.calls[-1]["args"] == {"window": 1}


EVENTS = json.loads((__import__("pathlib").Path(__file__).parent / "fixtures" / "events.json").read_text())


@pytest.mark.parametrize("case", EVENTS, ids=[c["name"] for c in EVENTS])
def test_every_host_event_is_accepted(native, case):
    app = QApplication([])
    app._dispatch(case["json"])


def test_click_event_from_fixture_reaches_its_button(native):
    app = QApplication([])
    button, got = QPushButton("+"), []
    button.clicked.connect(lambda: got.append(True))
    widgets._widgets["inc"] = button
    click = next(c for c in EVENTS if c["name"] == "click")
    app._dispatch(click["json"])
    assert got == [True]

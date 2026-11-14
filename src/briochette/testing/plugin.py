"""pytest plugin: a pytest-qt-compatible ``qtbot`` over the headless host."""

import os
import subprocess
import time

import pytest

from briochette.core import Qt
from briochette.testing import HeadlessHost, app_dir
from briochette.widgets import QApplication


class QtBot:
    """Drives widgets as a user would, through the events the host sends."""

    def __init__(self, app):
        self._app = app
        self._widgets = []

    @property
    def host(self):
        return self._app._host

    def addWidget(self, widget):
        """Shows `widget` headlessly and closes it when the test ends."""
        widget.show()
        self._widgets.append(widget)

    def wait(self, ms=0):
        """Lets queued updates reach the host."""
        self._app.flush()

    def mouseClick(self, widget, button=Qt.MouseButton.LeftButton, modifier=None, pos=None, delay=-1):
        """Clicks `widget`, sending the host's click event for its node."""
        window, node = self._node(widget, widget._click_path())
        if button != Qt.MouseButton.LeftButton:
            return
        attrs = node["a"]
        assert "disabled" not in attrs, f"{widget!r} is disabled"
        assert "phx-click" in attrs, f"{widget!r} does not handle clicks"
        values = {k.removeprefix("phx-value-"): v for k, v in attrs.items() if k.startswith("phx-value-")}
        if node["t"] == "input" and attrs.get("type") == "checkbox":
            values["checked"] = "checked" not in attrs
        self._send(window, "click", attrs["phx-click"], values)

    def keyClicks(self, widget, text, modifier=None, delay=-1):
        """Types `text` at the end of a text input, as the host reports typing."""
        window, node = self._node(widget, widget._click_path())
        attrs = node["a"]
        assert node["t"] in ("input", "textarea") and "phx-change" in attrs, (
            f"{widget!r} is not a text input"
        )
        assert "disabled" not in attrs, f"{widget!r} is disabled"
        name = attrs.get("name", "value")
        self._send(window, "change", attrs["phx-change"], {name: widget.text() + text, "_target": name})

    def keyClick(self, widget, key, modifier=None, delay=-1):
        """Presses `key` in `widget`: Return or Enter submits a text input's form."""
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            window, form = self._node(widget, [])
            assert "phx-submit" in form["a"], f"{widget!r} does not handle Enter"
            self._send(window, "submit", form["a"]["phx-submit"], {"value": widget.text()})

    def _node(self, widget, sub):
        """(window, node) for `widget`'s node, or its descendant at `sub`."""
        self._app.flush()
        loc = widget._location()
        assert loc, f"{widget!r} is not shown; pass it or its window to qtbot.addWidget"
        window, path = loc
        node = self.host.tree(window)
        for i in path + sub:
            node = node["c"][i]
        return window, node

    def _send(self, window, kind, event, values):
        self._app._dispatch({"type": kind, "window": window, "event": event, "values": values})
        self._app.flush()

    def _close_all(self):
        for widget in self._widgets:
            widget.close()


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([], host=HeadlessHost())


@pytest.fixture
def qtbot(qapp):
    bot = QtBot(qapp)
    yield bot
    bot._close_all()


@pytest.fixture
def app_page(request, tmp_path):
    """The app's main window as a Playwright page, in the real host.

    Runs the host named by ``BRIOCHETTE_HOST`` (built with its ``playwright``
    feature) on the project's app, and connects playwright-python to it.
    Needs a display (``xvfb-run -a`` on Linux CI).
    """
    host = os.environ.get("BRIOCHETTE_HOST")
    if not host:
        pytest.skip("set BRIOCHETTE_HOST to a host built with the playwright feature")
    from playwright.sync_api import sync_playwright

    root = app_dir(_project(request.path), tmp_path / "app")
    endpoint_file = tmp_path / "endpoint"
    log = open(tmp_path / "host.log", "wb")
    env = {
        **os.environ,
        "BRIOCHETTE_APP": str(root),
        "GPUI_PLAYWRIGHT": "127.0.0.1:0",
        "GPUI_PLAYWRIGHT_ENDPOINT_FILE": str(endpoint_file),
    }
    process = subprocess.Popen([host], env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        endpoint = _await_endpoint(endpoint_file, process, tmp_path / "host.log")
        with sync_playwright() as p:
            browser = p.chromium.connect(endpoint)
            yield browser.new_context().new_page()
            browser.close()
    finally:
        process.terminate()
        process.wait(10)
        log.close()


def _project(test_file):
    """The nearest directory above `test_file` whose pyproject.toml has [tool.briochette]."""
    for directory in test_file.parents:
        pyproject = directory / "pyproject.toml"
        if pyproject.is_file() and "[tool.briochette]" in pyproject.read_text():
            return directory
    pytest.fail(f"no pyproject.toml with [tool.briochette] above {test_file}")


def _await_endpoint(path, process, log, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and (endpoint := path.read_text().strip()):
            return endpoint
        if process.poll() is not None:
            break
        time.sleep(0.1)
    pytest.fail(f"the host gave no playwright endpoint; its log:\n{log.read_text()}")

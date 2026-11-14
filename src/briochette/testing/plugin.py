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
        self._app.flush()
        loc = widget._location()
        assert loc, f"{widget!r} is not shown; pass it or its window to qtbot.addWidget"
        window, path = loc
        node = self.host.tree(window)
        for i in path:
            node = node["c"][i]
        if button != Qt.MouseButton.LeftButton:
            return
        attrs = node["a"]
        assert "phx-click" in attrs, f"{widget!r} does not handle clicks"
        values = {k.removeprefix("phx-value-"): v for k, v in attrs.items() if k.startswith("phx-value-")}
        self._app._dispatch({"type": "click", "window": window, "event": attrs["phx-click"], "values": values})
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

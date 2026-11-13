"""pytest plugin: a pytest-qt-compatible ``qtbot`` over the headless host."""

import pytest

from briochette.core import Qt
from briochette.testing import HeadlessHost
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

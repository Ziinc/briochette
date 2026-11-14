"""Widgets. Each widget owns one host node; setters patch only that node."""

import asyncio
import itertools
import json
import queue
import weakref

from briochette import _native
from briochette.core import QObject, pyqtSignal

__all__ = ["QApplication", "QWidget", "QLayout", "QVBoxLayout", "QLabel", "QPushButton"]

_ids = itertools.count()
# Widgets by the event name their node carries, to route host events back.
_widgets = weakref.WeakValueDictionary()


class QApplication(QObject):
    """Owns the host connection, the open windows and the event loop."""

    _instance = None

    def __init__(self, argv=None, host=None):
        super().__init__()
        if QApplication._instance is not None:
            raise RuntimeError("a QApplication already exists")
        QApplication._instance = self
        self._host = host if host is not None else _native.connect()
        self._windows = itertools.count()
        self._roots = {}
        self._pending = {}
        self._loop = None
        self._code = 0
        # Host events arrive on another thread; the loop drains them in order.
        self._inbox = queue.SimpleQueue()
        if hasattr(self._host, "set_event_handler"):
            self._host.set_event_handler(self._post)

    @staticmethod
    def instance():
        return QApplication._instance

    def exec(self):
        """Runs the event loop until `quit` or `exit`; returns the exit code."""
        self._loop = asyncio.new_event_loop()
        self._loop.call_soon(self._drain)
        try:
            self._loop.run_forever()
        finally:
            self.flush()
            self._loop.close()
            self._loop = None
        return self._code

    def exit(self, code=0):
        """Stops `exec`; safe to call from any thread."""
        self._code = code
        if loop := self._loop:
            loop.call_soon_threadsafe(loop.stop)

    def quit(self):
        self.exit(0)

    def flush(self):
        """Sends each window's patches queued since the last flush as one frame."""
        pending, self._pending = self._pending, {}
        for window, ops in pending.items():
            self._render(window, {"patch": ops})

    def _render(self, window, frame):
        if self._host is not None:
            self._host.render(window, frame)

    def _queue(self, window, op):
        first = not self._pending
        self._pending.setdefault(window, []).append(op)
        if first and self._loop is not None:
            # Setters in one step of the loop go out together.
            self._loop.call_soon(self.flush)

    def _open(self, widget):
        window = next(self._windows)
        self._roots[window] = widget
        self._render(window, {"root": widget._node()})
        return window

    def _close(self, window):
        self._pending.pop(window, None)
        self._roots.pop(window, None)
        if self._host is not None:
            self._host.close(window)

    def _post(self, event_json):
        """Called by the host on its own thread with each event's JSON."""
        self._inbox.put(json.loads(event_json))
        if loop := self._loop:
            loop.call_soon_threadsafe(self._drain)

    def _drain(self):
        while not self._inbox.empty():
            self._dispatch(self._inbox.get_nowait())

    def _dispatch(self, event):
        """Handles an event from the host, on the Python thread."""
        match event.get("type"):
            case "click":
                if widget := _widgets.get(event.get("event")):
                    widget._host_click()
            case "resync":
                # The host lost the window's tree: send it whole.
                window = event.get("window")
                if root := self._roots.get(window):
                    self._pending.pop(window, None)
                    self._render(window, {"root": root._node()})


def _app():
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("create a QApplication before showing widgets")
    return app


class QWidget(QObject):
    """A box. A widget without a parent opens a window when shown."""

    _tag = "div"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._id = f"w{next(_ids)}"
        self._layout = None
        self._window = None
        self._accessible_name = None

    # Qt API

    def setLayout(self, layout):
        self._layout = layout
        layout._owner = self
        for w in layout._items:
            w._parent = self
        self._emit({"op": "replace", "node": self._node()})

    def layout(self):
        return self._layout

    def setAccessibleName(self, name):
        self._accessible_name = name
        self._emit({"op": "attrs", "a": self._attrs()})

    def accessibleName(self):
        return self._accessible_name or ""

    def isWindow(self):
        return self._parent is None

    def winId(self):
        """The id of the host window this widget is in, or None if not shown."""
        loc = self._location()
        return loc and loc[0]

    def show(self):
        if self.isWindow() and self._window is None:
            self._window = _app()._open(self)

    def close(self):
        if self._window is not None:
            _app()._close(self._window)
            self._window = None
        return True

    # Rendering

    def _attrs(self):
        attrs = {}
        if self._accessible_name:
            attrs["aria-label"] = self._accessible_name
        classes = (["size-full"] if self.isWindow() else []) + (
            [self._layout._class] if self._layout else []
        )
        if classes:
            attrs["class"] = " ".join(classes)
        return attrs

    def _children(self):
        return [w._node() for w in self._layout._items] if self._layout else []

    def _node(self):
        return {"t": self._tag, "a": self._attrs(), "c": self._children()}

    def _location(self):
        """(window, path) of this widget's node, or None if it is not shown."""
        if self._window is not None:
            return self._window, []
        parent = self._parent
        if not isinstance(parent, QWidget) or not parent._layout:
            return None
        if self not in parent._layout._items or not (loc := parent._location()):
            return None
        return loc[0], loc[1] + [parent._layout.indexOf(self)]

    def _emit(self, op, sub=()):
        if loc := self._location():
            _app()._queue(loc[0], {"op": op["op"], "at": loc[1] + list(sub), **op})


class QLayout(QObject):
    """Arranges a widget's children; maps to a flex class on the owner's node."""

    _class = ""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._owner = None
        self._items = []
        if parent is not None:
            parent.setLayout(self)

    def addWidget(self, widget):
        self._items.append(widget)
        if self._owner is not None:
            widget._parent = self._owner
            self._owner._emit(
                {"op": "splice", "start": len(self._items) - 1, "delete": 0, "c": [widget._node()]}
            )

    def indexOf(self, widget):
        return self._items.index(widget)

    def count(self):
        return len(self._items)


class QVBoxLayout(QLayout):
    _class = "flex-col"


class _Text(QWidget):
    """A widget whose node holds one text child."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._text = text

    def text(self):
        return self._text

    def setText(self, text):
        old, self._text = self._text, text
        if old and text:
            self._emit({"op": "replace", "node": text}, sub=[0])
        else:
            self._emit({"op": "replace", "node": self._node()})

    def _children(self):
        return [self._text] if self._text else []


class QLabel(_Text):
    _tag = "text"


class QPushButton(_Text):
    _tag = "button"
    clicked = pyqtSignal(bool)

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        _widgets[self._id] = self

    def click(self):
        self.clicked.emit(False)

    def _host_click(self):
        self.click()

    def _attrs(self):
        return {**super()._attrs(), "phx-click": self._id}

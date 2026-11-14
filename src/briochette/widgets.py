"""Widgets. Each widget owns one host node; setters patch only that node."""

import asyncio
import itertools
import json
import queue
import weakref

from briochette import _native
from briochette.core import QObject, pyqtSignal

__all__ = [
    "QApplication",
    "QWidget",
    "QLayout",
    "QBoxLayout",
    "QVBoxLayout",
    "QHBoxLayout",
    "QGridLayout",
    "QLabel",
    "QPushButton",
    "QLineEdit",
    "QCheckBox",
    "QProgressBar",
]

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
            case "click" | "change" | "submit" as kind:
                if widget := _widgets.get(event.get("event")):
                    widget._on_host(kind, event.get("values") or {})
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
        self._enabled = True
        self._hidden = False
        # Set by the layout the widget is in, such as "flex-1" for a stretch.
        self._item_class = None

    # Qt API

    def setLayout(self, layout):
        self._layout = layout
        layout._owner = self
        for w in layout._widgets():
            w._parent = self
        self._refresh()

    def layout(self):
        return self._layout

    def setAccessibleName(self, name):
        self._accessible_name = name
        self._attrs_changed()

    def accessibleName(self):
        return self._accessible_name or ""

    def setEnabled(self, enabled):
        if enabled != self._enabled:
            self._enabled = enabled
            self._attrs_changed()

    def setDisabled(self, disabled):
        self.setEnabled(not disabled)

    def isEnabled(self):
        return self._enabled

    def isWindow(self):
        return self._parent is None

    def isVisible(self):
        if self.isWindow():
            return self._window is not None
        return not self._hidden and isinstance(self._parent, QWidget) and self._parent.isVisible()

    def winId(self):
        """The id of the host window this widget is in, or None if not shown."""
        loc = self._location()
        return loc and loc[0]

    def show(self):
        self.setVisible(True)

    def hide(self):
        self.setVisible(False)

    def setVisible(self, visible):
        if self.isWindow():
            if visible and self._window is None:
                self._window = _app()._open(self)
            elif not visible:
                self.close()
        elif self._hidden == visible:
            self._hidden = not visible
            self._refresh()

    def close(self):
        if self._window is not None:
            _app()._close(self._window)
            self._window = None
        return True

    # Rendering

    def _classes(self):
        classes = ["size-full"] if self.isWindow() else []
        if self._item_class:
            classes.append(self._item_class)
        if self._layout:
            classes += self._layout._classes()
        return classes

    def _attrs(self):
        attrs = {}
        if self._accessible_name:
            attrs["aria-label"] = self._accessible_name
        if not self._enabled:
            attrs["disabled"] = ""
        if classes := self._classes():
            attrs["class"] = " ".join(classes)
        return attrs

    def _children(self):
        return self._layout._children() if self._layout else []

    def _node(self):
        if self._hidden:
            return {"t": "div", "a": {"class": "hidden"}, "c": []}
        return {"t": self._tag, "a": self._attrs(), "c": self._children()}

    def _location(self):
        """(window, path) of this widget's node, or None if it is not shown."""
        if self._window is not None:
            return self._window, []
        parent = self._parent
        if not isinstance(parent, QWidget) or not parent._layout:
            return None
        sub = parent._layout._path_of(self)
        if sub is None or not (loc := parent._location()):
            return None
        return loc[0], loc[1] + sub

    def _emit(self, op, sub=()):
        if loc := self._location():
            _app()._queue(loc[0], {"op": op["op"], "at": loc[1] + list(sub), **op})

    def _refresh(self):
        """Sends this widget's node whole."""
        self._emit({"op": "replace", "node": self._node()})

    def _attrs_changed(self):
        if self._hidden:
            return
        self._emit({"op": "attrs", "a": self._attrs()})

    def _click_path(self):
        """Where in this widget's node a click lands."""
        return []

    def _on_host(self, kind, values):
        """An event from the host for this widget's node."""


class QLayout(QObject):
    """Arranges a widget's children; maps to flex classes on the owner's node."""

    _direction = "flex-col"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._owner = None
        self._items = []
        self._spacing = None
        self._margins = None
        if parent is not None:
            parent.setLayout(self)

    def setSpacing(self, spacing):
        self._spacing = spacing
        self._owner_attrs_changed()

    def spacing(self):
        return -1 if self._spacing is None else self._spacing

    def setContentsMargins(self, left, top, right, bottom):
        self._margins = (left, top, right, bottom)
        self._owner_attrs_changed()

    def addWidget(self, widget, stretch=0, alignment=None):
        widget._item_class = "flex-1" if stretch else None
        self._add(widget)

    def addLayout(self, layout, stretch=0):
        box = QWidget()
        box.setLayout(layout)
        self.addWidget(box, stretch)

    def addStretch(self, stretch=1):
        spacer = QWidget()
        spacer._item_class = "flex-1"
        self._add(spacer)

    def indexOf(self, widget):
        return self._items.index(widget)

    def count(self):
        return len(self._items)

    # Rendering

    def _classes(self):
        classes = [self._direction]
        if self._spacing is not None:
            classes.append(f"gap-[{self._spacing}px]")
        if self._margins is not None:
            classes += [f"{side}-[{n}px]" for side, n in zip(("pl", "pt", "pr", "pb"), self._margins)]
        return classes

    def _owner_attrs_changed(self):
        if self._owner is not None:
            self._owner._attrs_changed()

    def _widgets(self):
        return list(self._items)

    def _children(self):
        return [w._node() for w in self._items]

    def _path_of(self, widget):
        return [self._items.index(widget)] if widget in self._items else None

    def _add(self, widget):
        self._items.append(widget)
        if self._owner is not None:
            widget._parent = self._owner
            self._owner._emit(
                {"op": "splice", "start": len(self._items) - 1, "delete": 0, "c": [widget._node()]}
            )


class QBoxLayout(QLayout):
    pass


class QVBoxLayout(QBoxLayout):
    _direction = "flex-col"


class QHBoxLayout(QBoxLayout):
    _direction = "flex-row"


class QGridLayout(QLayout):
    """Rows of equal-width cells. Spans are accepted and not yet drawn."""

    def __init__(self, parent=None):
        self._cells = {}
        super().__init__(parent)

    def addWidget(self, widget, row=None, column=None, rowSpan=1, columnSpan=1, alignment=None):
        if row is None:
            row, column = self.rowCount(), 0
        self._cells[(row, column)] = widget
        if self._owner is not None:
            widget._parent = self._owner
            self._owner._refresh()

    def rowCount(self):
        return 1 + max((r for r, _ in self._cells), default=-1)

    def columnCount(self):
        return 1 + max((c for _, c in self._cells), default=-1)

    def count(self):
        return len(self._cells)

    def _widgets(self):
        return list(self._cells.values())

    def _children(self):
        def cell(r, c):
            w = self._cells.get((r, c))
            return {"t": "div", "a": {"class": "flex-1"}, "c": [w._node()] if w else []}

        columns = range(self.columnCount())
        return [
            {"t": "div", "a": {"class": "flex-row"}, "c": [cell(r, c) for c in columns]}
            for r in range(self.rowCount())
        ]

    def _path_of(self, widget):
        for (r, c), w in self._cells.items():
            if w is widget:
                return [r, c, 0]
        return None


class _Text(QWidget):
    """A widget whose node holds one text child."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._text = text

    def text(self):
        return self._text

    def setText(self, text):
        old, self._text = self._text, text
        if old and text and not self._hidden:
            self._emit({"op": "replace", "node": text}, sub=[0])
        else:
            self._refresh()

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
        if self._enabled:
            self.clicked.emit(False)

    def _on_host(self, kind, values):
        if kind == "click":
            self.click()

    def _attrs(self):
        return {**super()._attrs(), "phx-click": self._id}


class QLineEdit(QWidget):
    """A one-line text input: a form, so Enter submits, around the input."""

    _tag = "form"
    textChanged = pyqtSignal(str)
    textEdited = pyqtSignal(str)
    returnPressed = pyqtSignal()

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._text = text
        self._placeholder = ""
        _widgets[self._id] = self

    def text(self):
        return self._text

    def setText(self, text):
        if text != self._text:
            self._text = text
            self._attrs_changed()
            self.textChanged.emit(text)

    def clear(self):
        self.setText("")

    def placeholderText(self):
        return self._placeholder

    def setPlaceholderText(self, text):
        self._placeholder = text
        self._attrs_changed()

    def _attrs(self):
        attrs = {"phx-submit": self._id}
        if classes := self._classes():
            attrs["class"] = " ".join(classes)
        return attrs

    def _input_attrs(self):
        attrs = {"name": "value", "phx-change": self._id, "value": self._text}
        if self._placeholder:
            attrs["placeholder"] = self._placeholder
        if self._accessible_name:
            attrs["aria-label"] = self._accessible_name
        if not self._enabled:
            attrs["disabled"] = ""
        return attrs

    def _children(self):
        return [{"t": "input", "a": self._input_attrs(), "c": []}]

    def _attrs_changed(self):
        if not self._hidden:
            self._emit({"op": "attrs", "a": self._input_attrs()}, sub=[0])

    def _click_path(self):
        return [0]

    def _on_host(self, kind, values):
        if kind == "change":
            # The host already shows what was typed: no patch, or a late one
            # would overwrite newer typing.
            text = values.get("value", "")
            if text != self._text:
                self._text = text
                self.textEdited.emit(text)
                self.textChanged.emit(text)
        elif kind == "submit":
            self.returnPressed.emit()


class QCheckBox(QWidget):
    """A checkbox with its text beside it."""

    toggled = pyqtSignal(bool)
    stateChanged = pyqtSignal(int)
    clicked = pyqtSignal(bool)

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._text = text
        self._checked = False
        _widgets[self._id] = self

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text
        self._refresh()

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        if checked != self._checked:
            self._checked = checked
            self._attrs_changed()
            self.toggled.emit(checked)
            self.stateChanged.emit(2 if checked else 0)

    def _attrs(self):
        return {"class": " ".join(self._classes() + ["flex-row items-center gap-2"])}

    def _input_attrs(self):
        attrs = {
            "aria-label": self._accessible_name or self._text,
            "phx-click": self._id,
            "type": "checkbox",
        }
        if self._checked:
            attrs["checked"] = ""
        if not self._enabled:
            attrs["disabled"] = ""
        return attrs

    def _children(self):
        return [
            {"t": "input", "a": self._input_attrs(), "c": []},
            {"t": "text", "a": {}, "c": [self._text] if self._text else []},
        ]

    def _attrs_changed(self):
        if not self._hidden:
            self._emit({"op": "attrs", "a": self._input_attrs()}, sub=[0])

    def _click_path(self):
        return [0]

    def _on_host(self, kind, values):
        if kind == "click" and self._enabled:
            checked = bool(values.get("checked", not self._checked))
            self.setChecked(checked)
            self.clicked.emit(checked)


class QProgressBar(QWidget):
    valueChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min, self._max, self._value = 0, 100, 0

    def setRange(self, minimum, maximum):
        self._min, self._max = minimum, max(minimum, maximum)
        self.setValue(self._value)
        self._refresh()

    def setMinimum(self, minimum):
        self.setRange(minimum, max(minimum, self._max))

    def setMaximum(self, maximum):
        self.setRange(min(self._min, maximum), maximum)

    def minimum(self):
        return self._min

    def maximum(self):
        return self._max

    def value(self):
        return self._value

    def setValue(self, value):
        value = min(max(value, self._min), self._max)
        if value != self._value:
            self._value = value
            self._refresh()
            self.valueChanged.emit(value)

    def _attrs(self):
        return {
            **super()._attrs(),
            "aria-valuemax": str(self._max),
            "aria-valuemin": str(self._min),
            "aria-valuenow": str(self._value),
            "class": " ".join(self._classes() + ["h-2 w-full rounded-full bg-muted overflow-hidden"]),
            "role": "progressbar",
        }

    def _children(self):
        span = self._max - self._min
        percent = 100 * (self._value - self._min) / span if span else 0
        return [{"t": "div", "a": {"class": f"h-full bg-primary w-[{percent:g}%]"}, "c": []}]

"""Widgets. Each widget owns one host node; setters patch only that node."""

import asyncio
import enum
import itertools
import json
import queue
import threading
import weakref

from briochette import _native
from briochette.core import (
    QMimeData,
    QModelIndex,
    QObject,
    QPoint,
    QSize,
    Qt,
    QUrl,
    pyqtSignal,
)

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
    "QMenuBar",
    "QMenu",
    "QListView",
    "QMessageBox",
    "QFileDialog",
    "QSystemTrayIcon",
]

_ids = itertools.count()
# Widgets by the event name their node carries, to route host events back.
_widgets = weakref.WeakValueDictionary()


class QApplication(QObject):
    """Owns the host connection, the open windows and the event loop."""

    _instance = None
    applicationStateChanged = pyqtSignal(object)

    def __init__(self, argv=None, host=None):
        super().__init__()
        if QApplication._instance is not None:
            raise RuntimeError("a QApplication already exists")
        QApplication._instance = self
        self._host = host if host is not None else _native.connect()
        self._windows = itertools.count()
        self._roots = {}
        self._pending = {}
        # Windows whose whole frame (root and keymap) goes out at the next flush.
        self._stale = set()
        self._shortcuts = weakref.WeakSet()
        self._actions = weakref.WeakValueDictionary()
        self._menu_bar = None
        self._menus_stale = False
        self._refs = itertools.count()
        self._awaiting = {}
        self._clipboard = None
        # List views, whose visible rows go with every frame of their window.
        self._lists = weakref.WeakSet()
        # The GUI thread: the one that made the app. Its loop runs timers,
        # host events and signals from other threads.
        self._thread = threading.get_ident()
        self._loop = asyncio.new_event_loop()
        self._code = 0
        self._state = Qt.ApplicationState.ApplicationActive
        self._trays = weakref.WeakSet()
        # Host events arrive on another thread; the loop drains them in order.
        self._inbox = queue.SimpleQueue()
        if hasattr(self._host, "set_event_handler"):
            self._host.set_event_handler(self._post)

    @staticmethod
    def instance():
        return QApplication._instance

    def exec(self):
        """Runs the event loop until `quit` or `exit`; returns the exit code."""
        self._code = 0
        try:
            self._loop.run_forever()
        finally:
            self.flush()
        return self._code

    def exit(self, code=0):
        """Stops `exec`; safe to call from any thread."""
        self._code = code
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def quit(self):
        self.exit(0)

    def processEvents(self, seconds=0):
        """Runs the loop for `seconds` (timers, host events, queued signals)."""
        if not self._loop.is_running():
            self._loop.run_until_complete(asyncio.sleep(seconds))
        self.flush()

    def applicationState(self):
        return self._state

    @staticmethod
    def clipboard():
        app = _app()
        if app._clipboard is None:
            from briochette.gui import QClipboard

            app._clipboard = QClipboard()
        return app._clipboard

    def flush(self):
        """Sends each window's patches queued since the last flush as one frame."""
        pending, self._pending = self._pending, {}
        stale, self._stale = self._stale, set()
        for window in stale:
            pending.pop(window, None)
            if window in self._roots:
                self._render(window, self._frame(window))
        for window, ops in pending.items():
            frame = {"patch": ops}
            if lists := self._list_rows(window):
                frame["lists"] = lists
            self._render(window, frame)
        if self._menus_stale:
            self._menus_stale = False
            menus = self._menu_bar._spec() if self._menu_bar else []
            self._call("menu.set", {"menus": menus})

    def _frame(self, window):
        frame = {"root": self._roots[window]._node()}
        if keymap := self._keymap(window):
            frame["keymap"] = keymap
        if lists := self._list_rows(window):
            frame["lists"] = lists
        return frame

    def _list_rows(self, window):
        """The rows on screen of each list in `window`: the host keeps only
        what a frame carries, and asks for the rest."""
        return {
            view._id: view._segment(*view._visible)
            for view in self._lists
            if view._visible and view.winId() == window
        }

    def _lists_changed(self, window):
        """Sends `window` a frame, if only to carry its lists' rows."""
        if window is not None and window not in self._pending:
            if not self._pending and not self._stale:
                self._loop.call_soon(self.flush)
            self._pending[window] = []

    def _keymap(self, window):
        root = self._roots.get(window)
        return [
            {"keys": s._key._keys(), "action": s._id}
            for s in sorted(self._shortcuts, key=lambda s: int(s._id[1:]))
            if s._enabled
            and not s._key.isEmpty()
            and isinstance(s._parent, QWidget)
            and s._parent.window() is root
        ]

    def _add_shortcut(self, shortcut):
        self._shortcuts.add(shortcut)
        self._keymap_changed(shortcut._parent)

    def _keymap_changed(self, widget):
        if isinstance(widget, QWidget) and (window := widget.window()._window) is not None:
            self._mark_stale(window)

    def _mark_stale(self, window):
        if not self._stale and not self._pending:
            self._loop.call_soon(self.flush)
        self._stale.add(window)

    def _menus_changed(self):
        if not self._menus_stale:
            self._menus_stale = True
            self._loop.call_soon(self.flush)

    def _call(self, name, args):
        """A platform call; returns its ref. The reply arrives as an event."""
        ref = next(self._refs)
        if self._host is not None and hasattr(self._host, "call"):
            self._host.call({"call": name, "ref": ref, "args": args})
        return ref

    def _call_sync(self, name, args, timeout=5):
        """A platform call, waiting for its reply while handling other events.
        `timeout` None waits as long as it takes (a dialog the user answers)."""
        if self._host is None:
            return None
        ref = self._call(name, args)
        self._awaiting[ref] = None
        try:
            while self._awaiting[ref] is None:
                try:
                    event = self._inbox.get(timeout=timeout)
                except queue.Empty:
                    raise TimeoutError(f"no reply to {name} within {timeout} s") from None
                self._dispatch(event)
            reply = self._awaiting[ref]
        finally:
            self._awaiting.pop(ref, None)
        if reply.get("error"):
            raise RuntimeError(reply["error"])
        return reply.get("result")

    def _render(self, window, frame):
        if self._host is not None:
            self._host.render(window, frame)

    def _queue(self, window, op):
        first = not self._pending
        self._pending.setdefault(window, []).append(op)
        if first:
            # Setters in one step of the loop go out together.
            self._loop.call_soon(self.flush)

    def _open(self, widget):
        window = next(self._windows)
        self._roots[window] = widget
        if window != 0:
            # The host opens window 0 itself, from app.json.
            self._call("window.open", {"window": window, "title": widget.windowTitle()})
        self._render(window, self._frame(window))
        return window

    def _close(self, window):
        self._pending.pop(window, None)
        self._stale.discard(window)
        self._roots.pop(window, None)
        self._call("window.close", {"window": window})

    def _post(self, event_json):
        """Called by the host on its own thread with each event's JSON."""
        self._inbox.put(json.loads(event_json))
        self._loop.call_soon_threadsafe(self._drain)

    def _drain(self):
        while not self._inbox.empty():
            self._dispatch(self._inbox.get_nowait())

    def _dispatch(self, event):
        """Handles an event from the host, on the Python thread."""
        match event.get("type"):
            case "click" | "change" | "submit" as kind:
                if widget := _widgets.get(event.get("event")):
                    widget._on_host(kind, event.get("values") or {})
            case "rows":
                if view := _widgets.get(event.get("event")):
                    view._on_rows(event)
            case "action":
                for shortcut in list(self._shortcuts):
                    if shortcut._id == event.get("action") and shortcut._enabled:
                        shortcut.activated.emit()
            case "menu":
                if action := self._actions.get(event.get("event")):
                    action.trigger()
            case "window":
                self._on_window(event)
            case "tray":
                for tray in list(self._trays):
                    tray._on_host(event.get("event"))
            case "reply":
                if event.get("ref") in self._awaiting:
                    self._awaiting[event["ref"]] = event
            case "resync":
                # The host lost the window's tree: send it whole.
                window = event.get("window")
                if window in self._roots:
                    self._pending.pop(window, None)
                    self._render(window, self._frame(window))


    def _on_window(self, event):
        match event.get("event"):
            case "suspended":
                self._set_state(Qt.ApplicationState.ApplicationSuspended)
            case "resumed":
                self._set_state(Qt.ApplicationState.ApplicationActive)
            case _:
                if root := self._roots.get(event.get("window")):
                    root._on_window(event)

    def _set_state(self, state):
        if state != self._state:
            self._state = state
            self.applicationStateChanged.emit(state)


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
        self._size = QSize()
        self._pos = QPoint()
        self._accept_drops = False

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

    def window(self):
        """The top-level widget this one is in."""
        widget = self
        while isinstance(widget._parent, QWidget):
            widget = widget._parent
        return widget

    def setWindowTitle(self, title):
        self._title = title
        if self._window is not None:
            _app()._call("window.set_title", {"window": self._window, "title": title})

    def windowTitle(self):
        return getattr(self, "_title", "")

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
                if type(self).closeEvent is not QWidget.closeEvent:
                    # The window asks before closing: `closeEvent` decides.
                    self._window_call("window.prevent_close", on=True)
            elif not visible:
                self.close()
        elif self._hidden == visible:
            self._hidden = not visible
            self._refresh()

    def deleteLater(self):
        """Takes the widget out of its layout and window; Python frees it."""
        parent = self._parent
        if isinstance(parent, QWidget) and parent._layout and parent._layout._path_of(self):
            parent._layout.removeWidget(self)
        self.close()
        _widgets.pop(self._id, None)

    def close(self):
        if self._window is not None:
            _app()._close(self._window)
            self._window = None
        return True

    # Window geometry and state (top-level widgets)

    def size(self):
        return self._size

    def width(self):
        return self._size.width()

    def height(self):
        return self._size.height()

    def pos(self):
        return self._pos

    def x(self):
        return self._pos.x()

    def y(self):
        return self._pos.y()

    def resize(self, width, height=None):
        if isinstance(width, QSize):
            width, height = width.width(), width.height()
        self._window_call("window.set_bounds", width=width, height=height)

    def move(self, x, y=None):
        if isinstance(x, QPoint):
            x, y = x.x(), x.y()
        self._window_call("window.set_bounds", x=x, y=y)

    def setMinimumSize(self, width, height=None):
        if isinstance(width, QSize):
            width, height = width.width(), width.height()
        self._window_call("window.set_min_size", width=width, height=height)

    def showMaximized(self):
        self.show()
        self._window_call("window.maximize")

    def showMinimized(self):
        self.show()
        self._window_call("window.minimize")

    def showNormal(self):
        self.show()
        self._window_call("window.unmaximize")

    def showFullScreen(self):
        self.show()
        self._window_call("window.set_fullscreen", on=True)

    def activateWindow(self):
        self._window_call("window.focus")

    def raise_(self):
        self.activateWindow()

    def setWindowFlag(self, flag, on=True):
        if flag & Qt.WindowType.WindowStaysOnTopHint:
            self._window_call("window.set_always_on_top", on=on)

    def setAcceptDrops(self, on):
        self._accept_drops = on

    def acceptDrops(self):
        return self._accept_drops

    # Event handlers, for subclasses to override

    def closeEvent(self, event):
        event.accept()

    def resizeEvent(self, event):
        pass

    def moveEvent(self, event):
        pass

    def dropEvent(self, event):
        pass

    def _window_call(self, name, **args):
        if self._window is not None:
            _app()._call(name, {"window": self._window, **args})

    def _on_window(self, event):
        """A host event about this widget's window."""
        from briochette.gui import QCloseEvent, QDropEvent, QMoveEvent, QResizeEvent

        match event.get("event"):
            case "close-requested":
                close = QCloseEvent()
                self.closeEvent(close)
                if close.isAccepted():
                    self.close()
            case "closed":
                # The user closed it: the host already has.
                app = _app()
                app._roots.pop(self._window, None)
                app._pending.pop(self._window, None)
                self._window = None
            case "resized":
                old, self._size = self._size, QSize(event["width"], event["height"])
                self.resizeEvent(QResizeEvent(self._size, old))
            case "moved":
                old, self._pos = self._pos, QPoint(event["x"], event["y"])
                self.moveEvent(QMoveEvent(self._pos, old))
            case "drop" if self._accept_drops:
                urls = [QUrl.fromLocalFile(p) for p in event.get("paths", [])]
                self.dropEvent(QDropEvent(QPoint(event.get("x", 0), event.get("y", 0)), QMimeData(urls)))

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

    def removeWidget(self, widget):
        if widget not in self._items:
            return
        index = self._items.index(widget)
        if self._owner is not None:
            self._owner._emit({"op": "splice", "start": index, "delete": 1, "c": []})
        del self._items[index]
        widget._parent = None

    def indexOf(self, widget):
        return self._items.index(widget)

    def itemAt(self, index):
        return _LayoutItem(self._items[index]) if 0 <= index < len(self._items) else None

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


class _LayoutItem:
    def __init__(self, widget):
        self._widget = widget

    def widget(self):
        return self._widget


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

    def removeWidget(self, widget):
        for key, w in list(self._cells.items()):
            if w is widget:
                del self._cells[key]
                widget._parent = None
                if self._owner is not None:
                    self._owner._refresh()

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

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._pixmap = None

    def setPixmap(self, pixmap):
        self._pixmap = pixmap
        self._refresh()

    def pixmap(self):
        from briochette.gui import QPixmap

        return self._pixmap or QPixmap()

    def setText(self, text):
        self._pixmap = None
        super().setText(text)

    def _node(self):
        if self._pixmap is not None and not self._pixmap.isNull() and not self._hidden:
            return {"t": "img", "a": {**self._attrs(), "src": self._pixmap._src()}, "c": []}
        return super()._node()


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


class QMenuBar(QWidget):
    """The app's menu bar. Menus are native and app-wide; phones have none."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._menus = []
        _app()._menu_bar = self
        _app()._menus_changed()

    def addMenu(self, title):
        menu = title if isinstance(title, QMenu) else QMenu(title, self)
        self._menus.append(menu)
        _app()._menus_changed()
        return menu

    def _spec(self):
        return [menu._spec() for menu in self._menus]

    def _node(self):
        # Native, not part of the window's tree.
        return {"t": "div", "a": {"class": "hidden"}, "c": []}


class QMenu(QWidget):
    def __init__(self, title="", parent=None):
        if isinstance(title, QWidget):
            # QMenu(parent), as Qt also takes it.
            title, parent = "", title
        super().__init__(parent)
        self._title = title
        self._items = []

    def title(self):
        return self._title

    def addAction(self, action, slot=None):
        from briochette.gui import QAction

        if not isinstance(action, QAction):
            action = QAction(action, self)
        if slot is not None:
            action.triggered.connect(slot)
        self._items.append(action)
        _app()._menus_changed()
        return action

    def addSeparator(self):
        self._items.append(None)
        _app()._menus_changed()

    def _spec(self):
        return {"title": self._title.replace("&", ""), "items": self._item_specs()}

    def _item_specs(self):
        return [{"separator": True} if a is None else a._spec() for a in self._items]

    def exec(self, pos=None, at=None):
        """Shows the menu at the pointer, as a context menu. Its actions'
        `triggered` fire when chosen; this returns at once."""
        parent = self._parent
        window = parent.winId() if isinstance(parent, QWidget) else None
        _app()._call("menu.popup", {"window": window or 0, "items": self._item_specs()})

    def popup(self, pos=None, at=None):
        self.exec(pos, at)


class QListView(QWidget):
    """A model's rows in a virtualized list: the host asks for rows as they
    scroll into view, so a model may be long."""

    _tag = "list"
    clicked = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = None
        self._visible = None
        self._current = -1
        _widgets[self._id] = self
        _app()._lists.add(self)

    def model(self):
        return self._model

    def setModel(self, model):
        if self._model is not None:
            for signal in self._model_signals(self._model):
                signal.disconnect(self._model_changed)
        self._model = model
        for signal in self._model_signals(model):
            signal.connect(self._model_changed)
        self._model_changed()

    def currentIndex(self):
        return self._model.index(self._current) if self._model else QModelIndex()

    def setCurrentIndex(self, index):
        self._current = index.row()
        self._rows_changed()

    @staticmethod
    def _model_signals(model):
        return (model.dataChanged, model.rowsInserted, model.rowsRemoved, model.modelReset, model.layoutChanged)

    def _count(self):
        return self._model.rowCount() if self._model else 0

    def _model_changed(self, *args):
        self._attrs_changed()
        self._rows_changed()

    def _rows_changed(self):
        if loc := self._location():
            _app()._lists_changed(loc[0])

    def _attrs(self):
        classes = list(dict.fromkeys(["flex-1", *self._classes()]))
        return {
            **{k: v for k, v in super()._attrs().items() if k != "class"},
            "class": " ".join(classes),
            "id": self._id,
            "phx-rows": self._id,
            "rows": str(self._count()),
        }

    def _row(self, row):
        selected = row == self._current
        attrs = {
            "class": "px-2 py-1 bg-muted" if selected else "px-2 py-1",
            "phx-click": self._id,
            "phx-value-row": str(row),
            "role": "option",
        }
        if selected:
            attrs["aria-selected"] = "true"
        text = self._model.data(self._model.index(row), Qt.ItemDataRole.DisplayRole)
        return {"t": "div", "a": attrs, "c": [] if text is None else [str(text)]}

    def _segment(self, start, end):
        end = min(end, self._count())
        return {"id": self._id, "start": start, "rows": [self._row(i) for i in range(start, end)]}

    def _on_rows(self, event):
        self._visible = tuple(event.get("visible") or (event["start"], event["end"]))
        if loc := self._location():
            app = _app()
            app.flush()
            app._render(loc[0], {"rows": self._segment(event["start"], event["end"])})

    def _on_host(self, kind, values):
        if kind == "click" and self._model and "row" in values:
            index = self._model.index(int(values["row"]))
            if index.isValid():
                self.setCurrentIndex(index)
                self.clicked.emit(index)


def _filters(text):
    """Qt's name filters (``"Images (*.png *.jpg);;All files (*)"``) as the
    host's dialog filters."""
    import re

    filters = []
    for part in filter(None, (p.strip() for p in (text or "").split(";;"))):
        match = re.fullmatch(r"(.*?)\s*\(([^)]*)\)", part)
        name, patterns = (match.group(1), match.group(2)) if match else (part, part)
        extensions = [p.strip().removeprefix("*.").removeprefix("*") or "*" for p in patterns.split()]
        filters.append({"name": name or part, "extensions": extensions})
    return filters


def _first_filter(text):
    parts = [p.strip() for p in (text or "").split(";;") if p.strip()]
    return parts[0] if parts else ""


class QMessageBox(QWidget):
    """Native message and question dialogs."""

    class StandardButton(enum.IntFlag):
        NoButton = 0
        Ok = 0x00000400
        Save = 0x00000800
        Open = 0x00002000
        Yes = 0x00004000
        No = 0x00010000
        Abort = 0x00040000
        Retry = 0x00080000
        Ignore = 0x00100000
        Close = 0x00200000
        Cancel = 0x00400000
        Discard = 0x00800000

    class Icon(enum.Enum):
        NoIcon = 0
        Information = 1
        Warning = 2
        Critical = 3
        Question = 4

    @staticmethod
    def _message(title, text, kind):
        _app()._call_sync("dialog.message", {"title": title, "message": text, "kind": kind}, timeout=None)
        return QMessageBox.StandardButton.Ok

    @staticmethod
    def information(parent, title, text, buttons=None, default=None):
        return QMessageBox._message(title, text, "info")

    @staticmethod
    def warning(parent, title, text, buttons=None, default=None):
        return QMessageBox._message(title, text, "warning")

    @staticmethod
    def critical(parent, title, text, buttons=None, default=None):
        return QMessageBox._message(title, text, "error")

    @staticmethod
    def about(parent, title, text):
        QMessageBox._message(title, text, "info")

    @staticmethod
    def question(parent, title, text, buttons=None, default=None):
        """Two of `buttons` (Yes and No by default): the first, as the host's
        OK, or the second."""
        B = QMessageBox.StandardButton
        buttons = buttons or (B.Yes | B.No)
        chosen = [b for b in B if b and b in buttons][:2] or [B.Yes, B.No]
        ok, cancel = chosen[0], chosen[-1] if len(chosen) > 1 else B.Cancel
        yes = _app()._call_sync(
            "dialog.confirm",
            {"title": title, "message": text, "kind": "info", "ok": ok.name, "cancel": cancel.name},
            timeout=None,
        )
        return ok if yes else cancel


class QFileDialog(QWidget):
    """Native open and save dialogs. Each returns what Qt's does: a path
    ("" for a cancel) and the first filter."""

    @staticmethod
    def _args(caption, directory, filter_text):
        args = {}
        if caption:
            args["title"] = caption
        if directory:
            args["default_path"] = directory
        if filters := _filters(filter_text):
            args["filters"] = filters
        return args

    @staticmethod
    def getOpenFileName(parent=None, caption="", directory="", filter="", *rest, **kw):
        path = _app()._call_sync("dialog.open", QFileDialog._args(caption, directory, filter), timeout=None)
        return (path, _first_filter(filter)) if path else ("", "")

    @staticmethod
    def getOpenFileNames(parent=None, caption="", directory="", filter="", *rest, **kw):
        args = {**QFileDialog._args(caption, directory, filter), "multiple": True}
        paths = _app()._call_sync("dialog.open", args, timeout=None) or []
        return (list(paths), _first_filter(filter))

    @staticmethod
    def getExistingDirectory(parent=None, caption="", directory="", *rest, **kw):
        args = {**QFileDialog._args(caption, directory, ""), "directory": True}
        return _app()._call_sync("dialog.open", args, timeout=None) or ""

    @staticmethod
    def getSaveFileName(parent=None, caption="", directory="", filter="", *rest, **kw):
        import os

        args = QFileDialog._args(caption, os.path.dirname(directory), filter)
        if name := os.path.basename(directory):
            args["default_name"] = name
        path = _app()._call_sync("dialog.save", args, timeout=None)
        return (path, _first_filter(filter)) if path else ("", "")


class QSystemTrayIcon(QObject):
    """The app's icon in the system tray (desktop), with a menu and
    notifications."""

    class ActivationReason(enum.Enum):
        Unknown = 0
        Context = 1
        DoubleClick = 2
        Trigger = 3
        MiddleClick = 4

    class MessageIcon(enum.Enum):
        NoIcon = 0
        Information = 1
        Warning = 2
        Critical = 3

    activated = pyqtSignal(object)
    messageClicked = pyqtSignal()

    def __init__(self, icon=None, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._tooltip = ""
        self._menu = None
        self._visible = False
        _app()._trays.add(self)

    @staticmethod
    def isSystemTrayAvailable():
        return True

    def setIcon(self, icon):
        self._icon = icon
        self._changed()

    def icon(self):
        return self._icon

    def setToolTip(self, tip):
        self._tooltip = tip
        self._changed()

    def toolTip(self):
        return self._tooltip

    def setContextMenu(self, menu):
        self._menu = menu
        self._changed()

    def contextMenu(self):
        return self._menu

    def isVisible(self):
        return self._visible

    def setVisible(self, visible):
        self._visible = visible
        if visible:
            self._changed()
        else:
            _app()._call("tray.remove", {})

    def show(self):
        self.setVisible(True)

    def hide(self):
        self.setVisible(False)

    def showMessage(self, title, message, icon=None, msecs=10000):
        _app()._call("notification.send", {"title": title, "body": message})

    def _changed(self):
        if not self._visible:
            return
        spec = {"items": self._menu._item_specs() if self._menu else []}
        if self._icon is not None and not self._icon.isNull():
            spec["icon"] = self._icon._path
        if self._tooltip:
            spec["tooltip"] = self._tooltip
        _app()._call("tray.set", spec)

    def _on_host(self, event):
        reason = {"click": self.ActivationReason.Trigger, "double-click": self.ActivationReason.DoubleClick}.get(event)
        if reason is not None and self._visible:
            self.activated.emit(reason)

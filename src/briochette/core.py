"""Core classes: objects, signals and the ``Qt`` namespace."""

import enum
import inspect
import sys
import threading

__all__ = [
    "Qt",
    "QObject",
    "pyqtSignal",
    "QTimer",
    "QThread",
    "QModelIndex",
    "QAbstractItemModel",
    "QAbstractListModel",
    "QStringListModel",
    "pyqtSlot",
    "pyqtProperty",
    "Signal",
    "Slot",
    "Property",
    "QSize",
    "QPoint",
    "QUrl",
    "QMimeData",
    "QStandardPaths",
]


def _app():
    """The QApplication, if one exists (without importing the widgets)."""
    widgets = sys.modules.get("briochette.widgets")
    return widgets.QApplication.instance() if widgets else None


class Qt:
    """Enums used across the API."""

    class MouseButton(enum.Flag):
        NoButton = 0
        LeftButton = 1
        RightButton = 2
        MiddleButton = 4

    class ItemDataRole(enum.IntEnum):
        DisplayRole = 0
        DecorationRole = 1
        EditRole = 2
        ToolTipRole = 3
        UserRole = 0x0100

    class KeyboardModifier(enum.Flag):
        NoModifier = 0
        ShiftModifier = 0x02000000
        ControlModifier = 0x04000000
        AltModifier = 0x08000000
        MetaModifier = 0x10000000

    class WindowType(enum.Flag):
        Widget = 0
        Window = 0x1
        WindowStaysOnTopHint = 0x00040000

    class ApplicationState(enum.Enum):
        ApplicationSuspended = 0
        ApplicationHidden = 1
        ApplicationInactive = 2
        ApplicationActive = 4

    Key = enum.IntEnum(
        "Key",
        {
            "Key_Escape": 0x01000000,
            "Key_Tab": 0x01000001,
            "Key_Backspace": 0x01000003,
            "Key_Return": 0x01000004,
            "Key_Enter": 0x01000005,
            "Key_Delete": 0x01000007,
            "Key_Home": 0x01000010,
            "Key_End": 0x01000011,
            "Key_Left": 0x01000012,
            "Key_Up": 0x01000013,
            "Key_Right": 0x01000014,
            "Key_Down": 0x01000015,
            "Key_PageUp": 0x01000016,
            "Key_PageDown": 0x01000017,
            "Key_Space": 0x20,
            "Key_Plus": 0x2B,
            "Key_Minus": 0x2D,
            **{f"Key_{d}": 0x30 + d for d in range(10)},
            **{f"Key_{chr(c)}": c for c in range(ord("A"), ord("Z") + 1)},
            **{f"Key_F{n}": 0x01000030 + n - 1 for n in range(1, 13)},
        },
        module=__name__,
        qualname="Qt.Key",
    )


def _arity(slot):
    """How many positional arguments `slot` accepts, or None for any number."""
    try:
        params = inspect.signature(slot).parameters.values()
    except (TypeError, ValueError):
        return None
    count = 0
    for p in params:
        if p.kind is p.VAR_POSITIONAL:
            return None
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD):
            count += 1
    return count


class BoundSignal:
    """A signal on one object: slots connect to it, and `emit` calls them in order."""

    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append((slot, _arity(slot)))

    def disconnect(self, slot=None):
        if slot is None:
            self._slots.clear()
            return
        for i, (s, _) in enumerate(self._slots):
            if s == slot:
                del self._slots[i]
                return
        raise TypeError("disconnect() failed: the slot is not connected")

    def emit(self, *args):
        app = _app()
        if app is not None and threading.get_ident() != app._thread:
            # From another thread: slots run on the GUI thread, in order.
            app._loop.call_soon_threadsafe(self._deliver, args)
        else:
            self._deliver(args)

    def _deliver(self, args):
        # A slot may take fewer arguments than the signal carries.
        for slot, arity in list(self._slots):
            slot(*(args if arity is None else args[:arity]))


class pyqtSignal:
    """Declares a signal on a class; each instance gets its own `BoundSignal`."""

    def __init__(self, *types, name=None):
        self.types = types
        self.name = name

    def __set_name__(self, owner, name):
        self.attr = "_signal_" + name
        self.name = self.name or name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        try:
            return obj.__dict__[self.attr]
        except KeyError:
            bound = obj.__dict__[self.attr] = BoundSignal()
            return bound


def pyqtSlot(*types, name=None, result=None):
    """Marks a method as a slot. Any callable is a slot here, so it changes nothing."""

    def mark(function):
        return function

    return mark


class pyqtProperty(property):
    """A property; the type argument is accepted for compatibility."""

    def __init__(self, type=None, fget=None, fset=None, freset=None, fdel=None, doc=None, **kwargs):
        super().__init__(fget, fset, fdel, doc)
        self._type = type

    def __call__(self, fget):
        prop = pyqtProperty(self._type, fget, self.fset, None, self.fdel, self.__doc__)
        return prop

    def setter(self, fset):
        return pyqtProperty(self._type, self.fget, fset, None, self.fdel, self.__doc__)

    def deleter(self, fdel):
        return pyqtProperty(self._type, self.fget, self.fset, None, fdel, self.__doc__)


# PySide6's names for the same things.
Signal = pyqtSignal
Slot = pyqtSlot
Property = pyqtProperty


class QObject:
    """The base of every object that has a parent and signals.

    Keyword arguments connect signals: ``QAction("Open", triggered=slot)``.
    """

    def __init__(self, parent=None, **signals):
        self._parent = parent
        self._owned = []
        if parent is not None:
            # As in Qt, a parent owns its children: they live while it does.
            parent._owned.append(self)
        for name, slot in signals.items():
            signal = getattr(self, name, None)
            if not isinstance(signal, BoundSignal):
                raise TypeError(f"{type(self).__name__} has no signal {name!r}")
            signal.connect(slot)

    def parent(self):
        return self._parent

    def children(self):
        return list(self._owned)


class QTimer(QObject):
    """Emits `timeout` after an interval, once or repeatedly, on the app's loop."""

    timeout = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._interval = 0
        self._single = False
        self._handle = None

    @staticmethod
    def singleShot(msec, slot):
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(slot)
        timer.start(msec)

    def setInterval(self, msec):
        self._interval = msec

    def interval(self):
        return self._interval

    def setSingleShot(self, single):
        self._single = single

    def isSingleShot(self):
        return self._single

    def isActive(self):
        return self._handle is not None

    def start(self, msec=None):
        if msec is not None:
            self._interval = msec
        self.stop()
        app = _app()
        if app is None:
            raise RuntimeError("create a QApplication before starting timers")
        self._handle = app._loop.call_later(self._interval / 1000, self._fire)

    def stop(self):
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None

    def _fire(self):
        if self._single:
            self._handle = None
        else:
            self._handle = _app()._loop.call_later(self._interval / 1000, self._fire)
        self.timeout.emit()


class QThread(QObject):
    """Runs `run` on a thread of its own; its signals reach the GUI thread queued."""

    started = pyqtSignal()
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None

    def run(self):
        """Override: the work to do on the thread."""

    def start(self):
        if self.isRunning():
            return
        self._thread = threading.Thread(target=self._main, daemon=True)
        self._thread.start()

    def _main(self):
        self.started.emit()
        try:
            self.run()
        finally:
            self.finished.emit()

    def isRunning(self):
        return self._thread is not None and self._thread.is_alive()

    def isFinished(self):
        return self._thread is not None and not self._thread.is_alive()

    def wait(self, msecs=None):
        """Waits for `run` to return; True unless `msecs` passed first."""
        if self._thread is None:
            return True
        self._thread.join(None if msecs is None else msecs / 1000)
        return not self._thread.is_alive()


class QModelIndex:
    """A row (and column) of a model; invalid when made without one."""

    def __init__(self, row=-1, column=-1, model=None):
        self._row, self._column, self._model = row, column, model

    def row(self):
        return self._row

    def column(self):
        return self._column

    def model(self):
        return self._model

    def isValid(self):
        return self._model is not None and self._row >= 0

    def data(self, role=Qt.ItemDataRole.DisplayRole):
        return self._model.data(self, role) if self.isValid() else None

    def __eq__(self, other):
        return isinstance(other, QModelIndex) and (self._row, self._column, self._model) == (
            other._row,
            other._column,
            other._model,
        )

    def __hash__(self):
        return hash((self._row, self._column, id(self._model)))

    def __repr__(self):
        return f"QModelIndex(row={self._row}, column={self._column})"


class QAbstractItemModel(QObject):
    """Rows of data a view shows. Subclasses implement rowCount and data, and
    bracket changes with begin/end calls so views follow."""

    dataChanged = pyqtSignal(object, object, list)
    rowsInserted = pyqtSignal(object, int, int)
    rowsRemoved = pyqtSignal(object, int, int)
    modelReset = pyqtSignal()
    layoutChanged = pyqtSignal()

    def rowCount(self, parent=QModelIndex()):
        raise NotImplementedError

    def columnCount(self, parent=QModelIndex()):
        return 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        raise NotImplementedError

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        return False

    def index(self, row, column=0, parent=QModelIndex()):
        if 0 <= row < self.rowCount() and 0 <= column < self.columnCount():
            return QModelIndex(row, column, self)
        return QModelIndex()

    def beginInsertRows(self, parent, first, last):
        self._change = (parent, first, last)

    def endInsertRows(self):
        self.rowsInserted.emit(*self._change)

    def beginRemoveRows(self, parent, first, last):
        self._change = (parent, first, last)

    def endRemoveRows(self):
        self.rowsRemoved.emit(*self._change)

    def beginResetModel(self):
        pass

    def endResetModel(self):
        self.modelReset.emit()


class QAbstractListModel(QAbstractItemModel):
    pass


class QStringListModel(QAbstractListModel):
    """A list of strings, editable in place."""

    def __init__(self, strings=None, parent=None):
        super().__init__(parent)
        self._strings = list(strings or [])

    def rowCount(self, parent=QModelIndex()):
        return len(self._strings)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self._strings[index.row()]
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return False
        self._strings[index.row()] = value
        self.dataChanged.emit(index, index, [role])
        return True

    def insertRows(self, row, count, parent=QModelIndex()):
        if not 0 <= row <= len(self._strings):
            return False
        self.beginInsertRows(parent, row, row + count - 1)
        self._strings[row:row] = [""] * count
        self.endInsertRows()
        return True

    def removeRows(self, row, count, parent=QModelIndex()):
        if not (0 <= row and row + count <= len(self._strings)):
            return False
        self.beginRemoveRows(parent, row, row + count - 1)
        del self._strings[row : row + count]
        self.endRemoveRows()
        return True

    def stringList(self):
        return list(self._strings)

    def setStringList(self, strings):
        self.beginResetModel()
        self._strings = list(strings)
        self.endResetModel()


class QSize:
    """A width and a height; (-1, -1) is invalid."""

    def __init__(self, width=-1, height=-1):
        self._w, self._h = int(width), int(height)

    def width(self):
        return self._w

    def height(self):
        return self._h

    def isValid(self):
        return self._w >= 0 and self._h >= 0

    def __eq__(self, other):
        return isinstance(other, QSize) and (self._w, self._h) == (other._w, other._h)

    def __hash__(self):
        return hash((self._w, self._h))

    def __repr__(self):
        return f"QSize({self._w}, {self._h})"


class QPoint:
    def __init__(self, x=0, y=0):
        self._x, self._y = int(x), int(y)

    def x(self):
        return self._x

    def y(self):
        return self._y

    def __eq__(self, other):
        return isinstance(other, QPoint) and (self._x, self._y) == (other._x, other._y)

    def __hash__(self):
        return hash((self._x, self._y))

    def __repr__(self):
        return f"QPoint({self._x}, {self._y})"


class QUrl:
    """A URL; local files are ``file://`` URLs."""

    def __init__(self, url=""):
        self._url = url.toString() if isinstance(url, QUrl) else str(url)

    @staticmethod
    def fromLocalFile(path):
        from urllib.parse import quote

        return QUrl("file://" + quote(str(path)))

    def toString(self):
        return self._url

    def isLocalFile(self):
        return self._url.startswith("file://")

    def toLocalFile(self):
        from urllib.parse import unquote

        return unquote(self._url.removeprefix("file://")) if self.isLocalFile() else ""

    def scheme(self):
        return self._url.split(":", 1)[0] if ":" in self._url else ""

    def isValid(self):
        return bool(self._url)

    def __eq__(self, other):
        return isinstance(other, QUrl) and other._url == self._url

    def __hash__(self):
        return hash(self._url)

    def __repr__(self):
        return f"QUrl({self._url!r})"


class QMimeData(QObject):
    """What a drop carries: here, the files' URLs."""

    def __init__(self, urls=()):
        super().__init__()
        self._urls = list(urls)

    def hasUrls(self):
        return bool(self._urls)

    def urls(self):
        return list(self._urls)

    def setUrls(self, urls):
        self._urls = list(urls)


# `app.paths`'s key for each location the host knows.
_PATH_KEYS = {
    "DocumentsLocation": "documents",
    "PicturesLocation": "pictures",
    "TempLocation": "temp",
    "HomeLocation": "home",
    "AppLocalDataLocation": "local_data",
    "CacheLocation": "cache",
    "ConfigLocation": "config",
    "DownloadLocation": "downloads",
    "AppDataLocation": "data",
    "AppConfigLocation": "config",
}


class QStandardPaths:
    """Where the app keeps its files, and the user's folders, as the host
    reports them (``app.paths``)."""

    class StandardLocation(enum.Enum):
        DesktopLocation = 0
        DocumentsLocation = 1
        FontsLocation = 2
        ApplicationsLocation = 3
        MusicLocation = 4
        MoviesLocation = 5
        PicturesLocation = 6
        TempLocation = 7
        HomeLocation = 8
        AppLocalDataLocation = 9
        CacheLocation = 10
        GenericDataLocation = 11
        RuntimeLocation = 12
        ConfigLocation = 13
        DownloadLocation = 14
        GenericCacheLocation = 15
        GenericConfigLocation = 16
        AppDataLocation = 17
        AppConfigLocation = 18


    @staticmethod
    def writableLocation(location):
        """The folder's path, or "" where the host has none."""
        key = _PATH_KEYS.get(location.name)
        app = _app()
        if key is None or app is None:
            return ""
        return (app._call_sync("app.paths", {}) or {}).get(key) or ""

    @staticmethod
    def standardLocations(location):
        path = QStandardPaths.writableLocation(location)
        return [path] if path else []

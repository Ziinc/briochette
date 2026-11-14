"""Core classes: objects, signals and the ``Qt`` namespace."""

import enum
import inspect
import sys
import threading

__all__ = ["Qt", "QObject", "pyqtSignal", "QTimer", "QThread"]


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

    class Key(enum.IntEnum):
        Key_Escape = 0x01000000
        Key_Tab = 0x01000001
        Key_Backspace = 0x01000003
        Key_Return = 0x01000004
        Key_Enter = 0x01000005


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


class QObject:
    """The base of every object that has a parent and signals."""

    def __init__(self, parent=None):
        self._parent = parent

    def parent(self):
        return self._parent


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

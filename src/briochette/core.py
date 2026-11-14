"""Core classes: objects, signals and the ``Qt`` namespace."""

import enum
import inspect

__all__ = ["Qt", "QObject", "pyqtSignal"]


class Qt:
    """Enums used across the API."""

    class MouseButton(enum.Flag):
        NoButton = 0
        LeftButton = 1
        RightButton = 2
        MiddleButton = 4


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

"""Key sequences, shortcuts, actions and the clipboard."""

import itertools
import sys

from briochette.core import QObject, Qt, _app, pyqtSignal

__all__ = ["QKeySequence", "QShortcut", "QAction", "QClipboard"]

_ids = itertools.count()

_MODIFIERS = {"ctrl": "secondary", "shift": "shift", "alt": "alt"}
_KEYS = {
    "return": "enter",
    "enter": "enter",
    "esc": "escape",
    "del": "delete",
    "pgup": "pageup",
    "pgdown": "pagedown",
    "ins": "insert",
}


def _meta():
    # Qt's Meta is Control on macOS and the Windows/Super key elsewhere.
    return "ctrl" if sys.platform == "darwin" else "super"


class QKeySequence:
    """A shortcut such as ``"Ctrl+Shift+S"``; Ctrl is Command on macOS."""

    def __init__(self, text=""):
        self._text = text.toString() if isinstance(text, QKeySequence) else text

    def toString(self):
        return self._text

    def isEmpty(self):
        return not self._text

    def __eq__(self, other):
        return isinstance(other, QKeySequence) and other._text == self._text

    def __hash__(self):
        return hash(self._text)

    def __repr__(self):
        return f"QKeySequence({self._text!r})"

    def _keys(self):
        """In GPUI's keystroke syntax: ``secondary-shift-s``."""
        parts = self._text.split("+")
        if self._text.endswith("+") and len(parts) > 1:
            *mods, key = parts[:-2] + ["+"]
        else:
            *mods, key = parts
        names = []
        for mod in mods:
            mod = mod.strip().lower()
            names.append(_meta() if mod == "meta" else _MODIFIERS.get(mod, mod))
        key = key.strip().lower()
        return "-".join(names + [_KEYS.get(key, key)])


def _keys_from(key, modifier=None):
    """GPUI keystroke syntax for a Qt.Key and Qt.KeyboardModifier."""
    modifier = modifier or Qt.KeyboardModifier.NoModifier
    names = []
    if modifier & Qt.KeyboardModifier.ControlModifier:
        names.append("secondary")
    if modifier & Qt.KeyboardModifier.MetaModifier:
        names.append(_meta())
    if modifier & Qt.KeyboardModifier.AltModifier:
        names.append("alt")
    if modifier & Qt.KeyboardModifier.ShiftModifier:
        names.append("shift")
    name = Qt.Key(key).name.removeprefix("Key_").lower()
    name = {"return": "enter", "plus": "+", "minus": "-"}.get(name, name)
    return "-".join(names + [name])


def _sequence(key):
    return key if isinstance(key, QKeySequence) else QKeySequence(key)


class QShortcut(QObject):
    """A key sequence that emits `activated` while its widget's window is active."""

    activated = pyqtSignal()

    def __init__(self, key=None, parent=None, **signals):
        super().__init__(parent, **signals)
        self._id = f"s{next(_ids)}"
        self._key = _sequence(key or "")
        self._enabled = True
        app = _app()
        if app is not None:
            app._add_shortcut(self)

    def key(self):
        return self._key

    def setKey(self, key):
        self._key = _sequence(key)
        self._changed()

    def isEnabled(self):
        return self._enabled

    def setEnabled(self, enabled):
        self._enabled = enabled
        self._changed()

    def _changed(self):
        if (app := _app()) is not None:
            app._keymap_changed(self._parent)


class QAction(QObject):
    """A command with text and a shortcut, shown in menus."""

    triggered = pyqtSignal(bool)

    def __init__(self, text="", parent=None, **signals):
        super().__init__(parent, **signals)
        self._id = f"a{next(_ids)}"
        self._text = text
        self._shortcut = QKeySequence()
        self._enabled = True
        if (app := _app()) is not None:
            app._actions[self._id] = self

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text
        self._changed()

    def shortcut(self):
        return self._shortcut

    def setShortcut(self, key):
        self._shortcut = _sequence(key)
        self._changed()

    def isEnabled(self):
        return self._enabled

    def setEnabled(self, enabled):
        self._enabled = enabled

    def trigger(self):
        if self._enabled:
            self.triggered.emit(False)

    def _changed(self):
        if (app := _app()) is not None:
            app._menus_changed()

    def _spec(self):
        item = {"id": self._id, "label": self._text.replace("&&", "\0").replace("&", "").replace("\0", "&")}
        if not self._shortcut.isEmpty():
            item["keys"] = self._shortcut._keys()
        return item


class QClipboard(QObject):
    """The system clipboard's text, through the host."""

    def text(self):
        return _app()._call_sync("clipboard.read", {}) or ""

    def setText(self, text):
        _app()._call("clipboard.write", {"text": text})

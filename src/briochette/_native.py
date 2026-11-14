"""The host's C ABI, as the built-in `_briochette` module exposes it."""

import itertools
import json


class NativeHost:
    """Sends frames and platform calls to the host; window 0 is opened by the host."""

    def __init__(self, module):
        self._native = module
        self._refs = itertools.count()
        self._open = {0}

    def render(self, window, frame):
        if window not in self._open:
            self._open.add(window)
            self._call("window.open", {"window": window})
        self._native.render(window, json.dumps(frame, separators=(",", ":")))

    def close(self, window):
        self._open.discard(window)
        self._call("window.close", {"window": window})

    def set_event_handler(self, handler):
        """`handler` gets each event's JSON, on a thread that is not the app's."""
        self._native.set_event_handler(handler)

    def _call(self, name, args):
        message = {"call": name, "ref": next(self._refs), "args": args}
        self._native.call(json.dumps(message, separators=(",", ":")))


def connect():
    """The native host, when running inside one; otherwise None."""
    try:
        import _briochette
    except ImportError:
        return None
    return NativeHost(_briochette)

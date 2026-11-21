"""The host's C ABI, as the built-in `_briochette` module exposes it."""

import json


def _json(value):
    return json.dumps(value, separators=(",", ":"))


class NativeHost:
    """Sends frames and platform calls to the host."""

    def __init__(self, module):
        self._native = module

    def render(self, window, frame):
        self._native.render(window, _json(frame))

    def call(self, message):
        """A platform call, `{"call", "ref", "args"}`; its reply is an event."""
        self._native.call(_json(message))

    def set_event_handler(self, handler):
        """`handler` gets each event's JSON, on a thread that is not the app's."""
        self._native.set_event_handler(handler)


def connect():
    """The native host, when running inside one; otherwise None."""
    try:
        import _briochette
    except ImportError:
        return None
    return NativeHost(_briochette)

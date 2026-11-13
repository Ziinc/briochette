"""Headless testing: a host that keeps trees in memory, and the qtbot fixture."""

from briochette._wire import apply

__all__ = ["HeadlessHost"]


class HeadlessHost:
    """Applies frames as the host does, without drawing; records every frame."""

    def __init__(self):
        self._trees = {}
        self._frames = {}

    def render(self, window, frame):
        self._frames.setdefault(window, []).append(frame)
        if "root" in frame:
            self._trees[window] = frame["root"]
        else:
            self._trees[window] = apply(self._trees[window], frame["patch"])

    def close(self, window):
        self._trees.pop(window, None)

    def tree(self, window):
        """The node tree last rendered to `window`."""
        return self._trees.get(window)

    def frames(self, window):
        """Every frame sent to `window`, in order."""
        return list(self._frames.get(window, []))

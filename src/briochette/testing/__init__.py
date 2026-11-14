"""Headless testing: a host that keeps trees in memory, and the qtbot fixture."""

import json
import sysconfig
import tomllib
from pathlib import Path

from briochette._wire import apply

__all__ = ["HeadlessHost", "app_dir"]


def app_dir(project, dest, site_packages=None):
    """Lays out the project at `project` as the host runs an app, in `dest`.

    `app.json` comes from the project's `[tool.briochette]`; `site-packages`
    links to `site_packages`, by default this environment's, so the host
    imports the code under test.
    """
    pyproject = tomllib.loads((Path(project) / "pyproject.toml").read_text())
    config = pyproject.get("tool", {}).get("briochette")
    if not config or "app" not in config:
        raise ValueError(f"{project}/pyproject.toml has no [tool.briochette] app = \"module:function\"")
    root = Path(dest)
    root.mkdir(parents=True, exist_ok=True)
    app = {"app": config["app"]}
    if "window" in config:
        app["window"] = config["window"]
    (root / "app.json").write_text(json.dumps(app))
    site = Path(site_packages or sysconfig.get_path("purelib"))
    (root / "site-packages").symlink_to(site.resolve(), target_is_directory=True)
    return root


class HeadlessHost:
    """Applies frames as the host does, without drawing; records every frame
    and answers platform calls from memory."""

    def __init__(self):
        self._trees = {}
        self._frames = {}
        self._keymaps = {}
        self._rows = {}
        self._handler = None
        self.calls = []
        self.menus = []
        self.clipboard = ""

    def render(self, window, frame):
        self._frames.setdefault(window, []).append(frame)
        if "rows" in frame:
            segment = frame["rows"]
            rows = self._rows.setdefault(window, {}).setdefault(segment["id"], {})
            rows.update(enumerate(segment["rows"], segment["start"]))
            return
        if "root" in frame:
            self._trees[window] = frame["root"]
            self._keymaps[window] = frame.get("keymap", [])
        else:
            self._trees[window] = apply(self._trees[window], frame["patch"])
        # A frame's rows replace every list's: the others are stale.
        self._rows[window] = {
            key: dict(enumerate(segment["rows"], segment["start"]))
            for key, segment in frame.get("lists", {}).items()
        }

    def call(self, message):
        self.calls.append(message)
        name, args, result, error = message["call"], message.get("args", {}), None, None
        match name:
            case "clipboard.write":
                self.clipboard = args["text"]
            case "clipboard.read":
                result = self.clipboard
            case "menu.set":
                self.menus = args["menus"]
            case "window.close":
                self._trees.pop(args["window"], None)
            case "window.open" | "window.set_title" | "window.set_bounds" | "app.exit":
                pass
            case _:
                error = f"{name}: no platform call `{name}`"
        reply = {"type": "reply", "ref": message["ref"], "result": result}
        if error:
            reply["error"] = error
        if self._handler:
            self._handler(json.dumps(reply))

    def set_event_handler(self, handler):
        self._handler = handler

    def tree(self, window):
        """The node tree last rendered to `window`."""
        return self._trees.get(window)

    def keymap(self, window):
        """The key bindings of `window`'s last whole frame."""
        return self._keymaps.get(window, [])

    def rows(self, window, list_id):
        """The rows the host holds of a list, by index."""
        return dict(self._rows.get(window, {}).get(list_id, {}))

    def frames(self, window):
        """Every frame sent to `window`, in order."""
        return list(self._frames.get(window, []))

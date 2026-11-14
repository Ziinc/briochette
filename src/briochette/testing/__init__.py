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

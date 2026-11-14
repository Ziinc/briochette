import json

import pytest

from briochette.testing import app_dir


def test_app_json_from_pyproject(tmp_path):
    project = tmp_path / "counter"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[tool.briochette]\napp = "counter.app:main"\nwindow = { title = "Counter", width = 360 }\n'
    )
    site = tmp_path / "site"
    site.mkdir()
    root = app_dir(project, tmp_path / "app", site_packages=site)
    assert json.loads((root / "app.json").read_text()) == {
        "app": "counter.app:main",
        "window": {"title": "Counter", "width": 360},
    }
    assert (root / "site-packages").resolve() == site.resolve()


def test_no_tool_briochette_is_an_error(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    with pytest.raises(ValueError, match=r"\[tool.briochette\]"):
        app_dir(tmp_path, tmp_path / "app")

"""Staging an app for a phone: the directory levain embeds in the host."""

import hashlib
import json
import tarfile
from pathlib import Path

import pytest

from briochette import build

ROOT = Path(__file__).parent.parent
COUNTER = ROOT / "examples" / "counter"


def fake_stdlib(tmp_path):
    lib = tmp_path / "prefix" / "lib" / "python3.15"
    for name in ["os.py", "json/__init__.py", "lib-dynload/_json.so", "test/test_os.py", "idlelib/x.py", "tkinter/__init__.py"]:
        (lib / name).parent.mkdir(parents=True, exist_ok=True)
        (lib / name).write_text("")
    return lib


def test_stage_lays_out_app_json_site_packages_and_python(tmp_path):
    app = build.stage(COUNTER, tmp_path / "app", stdlib=fake_stdlib(tmp_path))
    assert json.loads((app / "app.json").read_text()) == {
        "app": "counter.app:main",
        "window": {"title": "Counter", "width": 360, "height": 240},
    }
    site = app / "site-packages"
    assert (site / "counter" / "app.py").is_file()
    assert (site / "briochette" / "widgets.py").is_file()
    lib = app / "python" / "lib" / "python3.15"
    assert (lib / "os.py").is_file() and (lib / "lib-dynload" / "_json.so").is_file()
    assert not any((lib / d).exists() for d in ["test", "idlelib", "tkinter"])
    assert not list(app.rglob("__pycache__"))


def test_stage_without_stdlib_ships_no_python(tmp_path):
    app = build.stage(COUNTER, tmp_path / "app")
    assert not (app / "python").exists()


def test_archive_has_the_app_at_its_root(tmp_path):
    app = build.stage(COUNTER, tmp_path / "app")
    out = build.archive(app, tmp_path / "app.tar.gz")
    with tarfile.open(out) as tar:
        names = tar.getnames()
    assert "app.json" in names and "site-packages/counter/app.py" in names


def test_fetch_checks_the_sha256(tmp_path, monkeypatch):
    payload = tmp_path / "src.tar.gz"
    with tarfile.open(payload, "w:gz") as tar:
        (tmp_path / "hello.txt").write_text("hi")
        tar.add(tmp_path / "hello.txt", "hello.txt")
    good = hashlib.sha256(payload.read_bytes()).hexdigest()
    monkeypatch.setattr(build, "_download", lambda url, to: to.write_bytes(payload.read_bytes()))

    root = build.fetch(build.Runtime("https://example.invalid/src.tar.gz", good), tmp_path / "cache")
    assert (root / "hello.txt").read_text() == "hi"

    with pytest.raises(ValueError, match="SHA-256"):
        build.fetch(build.Runtime("https://example.invalid/other.tar.gz", "0" * 64), tmp_path / "cache")


def test_runtimes_are_pinned_official_builds():
    for name, runtime in build.RUNTIMES.items():
        assert runtime.url.startswith("https://www.python.org/ftp/python/3.15.2/"), name
        assert len(runtime.sha256) == 64

"""Building an app for a phone: the app staged with its Python, and the
levain host built around it with levain-pack.

On Android and iOS the app ships inside the host library (levain's
``LEVAIN_APP_ARCHIVE``). The host links the official CPython build for the
platform, pinned here by SHA-256.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import briochette

__all__ = ["Runtime", "RUNTIMES", "fetch", "stage", "archive", "android", "ios"]

PYTHON = "3.15"


@dataclass(frozen=True)
class Runtime:
    url: str
    sha256: str


_FTP = "https://www.python.org/ftp/python/3.15.2"
RUNTIMES = {
    "android-x86_64": Runtime(
        f"{_FTP}/python-3.15.2-x86_64-linux-android.tar.gz",
        "e5b46c72295e558991bbe98415ac29bc1448aca35a8e660ddfe017e20305cbf8",
    ),
    "android-arm64": Runtime(
        f"{_FTP}/python-3.15.2-aarch64-linux-android.tar.gz",
        "cfd4f0fdaff465ba62ebf3c3df2c8c410d0802fef3f98897082460df704cfef6",
    ),
    "ios": Runtime(
        f"{_FTP}/python-3.15.2-iOS-XCframework.tar.gz",
        "0f9fc7f61ceb8278a69fc7ec6089aad81789a96fa42f31cfe6d2f5f860d20a62",
    ),
}

# Standard library parts no app needs (as the plan's slimming).
_DROP = {"test", "idlelib", "tkinter", "turtledemo", "ensurepip", "__pycache__"}


def _download(url, to):
    with urllib.request.urlopen(url) as response, open(to, "wb") as out:
        shutil.copyfileobj(response, out)


def fetch(runtime, cache):
    """Downloads and unpacks `runtime` into `cache` once; refuses a download
    whose SHA-256 is not the pinned one."""
    cache = Path(cache)
    root = cache / runtime.sha256
    if (root / ".complete").exists():
        return root
    cache.mkdir(parents=True, exist_ok=True)
    download = cache / Path(runtime.url).name
    _download(runtime.url, download)
    digest = hashlib.sha256(download.read_bytes()).hexdigest()
    if digest != runtime.sha256:
        download.unlink()
        raise ValueError(f"{runtime.url}: SHA-256 is {digest}, expected {runtime.sha256}")
    shutil.rmtree(root, ignore_errors=True)
    with tarfile.open(download) as tar:
        tar.extractall(root, filter="tar")
    download.unlink()
    (root / ".complete").touch()
    return root


def _config(project):
    pyproject = tomllib.loads((Path(project) / "pyproject.toml").read_text())
    config = pyproject.get("tool", {}).get("briochette")
    if not config or "app" not in config:
        raise ValueError(f'{project}/pyproject.toml has no [tool.briochette] app = "module:function"')
    return pyproject, config


def stage(project, dest, *, stdlib=None):
    """Lays out the app at `dest`: ``app.json``, the app and briochette in
    ``site-packages``, and with `stdlib` (a ``lib/python3.X`` directory) the
    Python it runs on in ``python/``."""
    _, config = _config(project)
    dest = Path(dest)
    shutil.rmtree(dest, ignore_errors=True)
    site = dest / "site-packages"
    site.mkdir(parents=True)
    app = {"app": config["app"], **({"window": config["window"]} if "window" in config else {})}
    (dest / "app.json").write_text(json.dumps(app))

    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("briochette build needs uv on PATH")
    subprocess.run(
        [uv, "pip", "install", "--quiet", "--no-deps", "--target", str(site), str(Path(project).resolve())],
        check=True,
    )
    ignore = shutil.ignore_patterns(*_DROP)
    shutil.copytree(Path(briochette.__file__).parent, site / "briochette", ignore=ignore, dirs_exist_ok=True)
    if stdlib is not None:
        stdlib = Path(stdlib)
        shutil.copytree(stdlib, dest / "python" / "lib" / stdlib.name, ignore=ignore)
    for cache in list(dest.rglob("__pycache__")):
        shutil.rmtree(cache)
    return dest


def archive(app, out):
    """The app as the ``.tar.gz`` levain embeds: its contents at the root."""
    out = Path(out)
    with tarfile.open(out, "w:gz") as tar:
        for path in sorted(Path(app).iterdir()):
            tar.add(path, path.name)
    return out


def _run(cmd, cwd=None, env=None):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, check=True)


def _tauri_config(project, out):
    pyproject, config = _config(project)
    name = pyproject["project"]["name"]
    window = config.get("window", {})
    # Tauri wants web assets though levain draws with GPUI: an empty page, by
    # absolute path, as the project it builds may be a generated wrapper.
    dist = Path(out).resolve() / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text("<!doctype html>\n")
    path = Path(out) / "tauri.mobile.json"
    path.write_text(
        json.dumps(
            {
                "productName": window.get("title", name),
                "version": pyproject["project"].get("version", "0.1.0"),
                "identifier": config.get("identifier", f"dev.briochette.{name}"),
                "build": {"frontendDist": str(dist)},
            }
        )
    )
    return name, path


ANDROID_ABIS = {
    "x86_64": {"triple": "x86_64-linux-android", "jni": "x86_64", "tauri": "x86_64", "runtime": "android-x86_64"},
    "arm64": {"triple": "aarch64-linux-android", "jni": "arm64-v8a", "tauri": "aarch64", "runtime": "android-arm64"},
}


def android(project, abi, host, out, *, levain_pack="levain-pack", cache=None, release=False):
    """Builds an APK of the app at `project` for `abi` (x86_64 or arm64) into
    `out`. `host` is briochette's host crate. Release builds are signed with
    the keystore in ``BRIOCHETTE_ANDROID_KEYSTORE`` and its ``_PASSWORD``,
    ``_KEY_ALIAS`` and ``_KEY_PASSWORD`` variables."""
    spec = ANDROID_ABIS[abi]
    out, host = Path(out).resolve(), Path(host).resolve()
    out.mkdir(parents=True, exist_ok=True)
    cache = Path(cache or Path.home() / ".cache" / "briochette")
    python = fetch(RUNTIMES[spec["runtime"]], cache) / "prefix"
    lib = python / "lib"

    app = stage(project, out / "app", stdlib=lib / f"python{PYTHON}")
    name, config = _tauri_config(project, out)
    env = {
        **os.environ,
        "LEVAIN_APP_ARCHIVE": str(archive(app, out / "app.tar.gz")),
        "PYO3_CROSS_LIB_DIR": str(lib),
        "PYO3_CROSS_PYTHON_VERSION": PYTHON,
    }
    init = [levain_pack, "init", "android", "--project", host, "--config", config]
    if release:
        init += ["--signing-env", "BRIOCHETTE_ANDROID"]
    _run(init, env=env)

    # The interpreter and the libraries its modules link, beside the host.
    jni = host / "gen/android/app/src/main/jniLibs" / spec["jni"]
    jni.mkdir(parents=True, exist_ok=True)
    for so in [*lib.glob(f"libpython{PYTHON}.so"), *lib.glob("lib*_python.so")]:
        shutil.copy2(so, jni / so.name)

    apk = out / f"{name}.apk"
    tauri = ["--apk", *([] if release else ["--debug"]), "--target", spec["tauri"]]
    _run([levain_pack, "build", "android", "--project", host, "--config", config, "--product", f"apk={apk}", "--", *tauri], env=env)
    return apk


IOS_TARGETS = {
    "sim": {"triple": "aarch64-apple-ios-sim", "tauri": "aarch64-sim", "slice": "ios-arm64_x86_64-simulator"},
    "device": {"triple": "aarch64-apple-ios", "tauri": "aarch64", "slice": "ios-arm64"},
}

# Runs after the app's resources are copied: CPython's own Xcode step puts the
# standard library in the bundle and each binary module in a framework.
_INSTALL_PYTHON = """\
    postBuildScripts:
      - name: Install Python
        basedOnDependencyAnalysis: false
        script: |
          set -e
          source "$PROJECT_DIR/Python.xcframework/build/utils.sh"
          install_python Python.xcframework
"""


def patch_project_yml(yml):
    """Embeds Python.xcframework in the app target and adds CPython's step."""
    target = "    type: application\n"
    if target not in yml:
        raise ValueError("project.yml has no application target")
    head, rest = yml.split(target, 1)
    depends = "    dependencies:\n"
    framework = "      - framework: Python.xcframework\n        embed: true\n"
    rest = rest.replace(depends, depends + framework, 1) if depends in rest else depends + framework + rest
    return head + target + _INSTALL_PYTHON + rest


def ios(project, kind, host, out, *, levain_pack="levain-pack", cache=None):
    """Builds the app at `project` for the simulator (``sim``: an unsigned
    ``.app``) or a device (``device``: an ``.ipa``, signed as Tauri signs with
    the ``APPLE_*`` variables the user sets) into `out`."""
    spec = IOS_TARGETS[kind]
    out, host = Path(out).resolve(), Path(host).resolve()
    out.mkdir(parents=True, exist_ok=True)
    cache = Path(cache or Path.home() / ".cache" / "briochette")
    framework = fetch(RUNTIMES["ios"], cache) / "Python.xcframework"
    slice_lib = framework / spec["slice"] / "lib-arm64"

    app = stage(project, out / "app")
    name, config = _tauri_config(project, out)
    archive_path = str(archive(app, out / "app.tar.gz"))
    env = {
        **os.environ,
        # Tauri's iOS build passes on only TAURI_-prefixed variables.
        "TAURI_LEVAIN_APP_ARCHIVE": archive_path,
        "LEVAIN_APP_ARCHIVE": archive_path,
        "PYO3_CROSS_LIB_DIR": str(slice_lib),
        "PYO3_CROSS_PYTHON_VERSION": PYTHON,
    }
    _run([levain_pack, "ios-crate", "--host-crate", "briochette_host", "--host-lib", "briochette_host_lib",
          "--host-path", host, "--out", out / "ios-crate"], env=env)
    project_dir = out / "ios-crate"
    _run([levain_pack, "init", "ios", "--project", project_dir, "--config", config,
          "--ldflags", f"-F{framework / spec['slice']}"], env=env)
    apple = project_dir / "gen/apple"
    shutil.copytree(framework, apple / "Python.xcframework", symlinks=True, dirs_exist_ok=True)
    yml = apple / "project.yml"
    yml.write_text(patch_project_yml(yml.read_text()))
    _run(["xcodegen", "generate"], cwd=apple)

    ext, product = ("app", out / f"{name}.app") if kind == "sim" else ("ipa", out / f"{name}.ipa")
    tauri = ["--target", spec["tauri"], *(["--debug"] if kind == "sim" else [])]
    _run([levain_pack, "build", "ios", "--project", project_dir, "--config", config,
          "--product", f"{ext}={product}", "--", *tauri], env=env)
    return product

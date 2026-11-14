"""An opt-in import hook: ``PyQt6.*`` imports resolve to briochette.

Runtime only: briochette publishes no package under that name. Call
``install()`` before the app imports PyQt6; nothing changes until then.
"""

import importlib
import importlib.abc
import importlib.util
import sys
import types

__all__ = ["install", "uninstall"]

MODULES = {
    "QtCore": "briochette.core",
    "QtGui": "briochette.gui",
    "QtWidgets": "briochette.widgets",
}
PACKAGES = ("PyQt6",)


class _Alias(importlib.abc.Loader):
    def __init__(self, target):
        self._target = target

    def create_module(self, spec):
        if self._target is None:
            package = types.ModuleType(spec.name)
            package.__path__ = []
            for sub, target in MODULES.items():
                setattr(package, sub, importlib.import_module(target))
            return package
        return importlib.import_module(self._target)

    def exec_module(self, module):
        pass


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        package, _, sub = name.partition(".")
        if package not in PACKAGES:
            return None
        if not sub:
            return importlib.util.spec_from_loader(name, _Alias(None), is_package=True)
        if sub not in MODULES:
            raise ImportError(f"briochette does not provide {name} (only {', '.join(MODULES)})", name=name)
        return importlib.util.spec_from_loader(name, _Alias(MODULES[sub]))


_finder = _Finder()


def install():
    """Makes ``PyQt6.QtCore``, ``QtGui`` and ``QtWidgets`` resolve to briochette."""
    if _finder not in sys.meta_path:
        sys.meta_path.insert(0, _finder)


def uninstall():
    if _finder in sys.meta_path:
        sys.meta_path.remove(_finder)

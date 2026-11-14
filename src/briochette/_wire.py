"""The wire format shared with the host, as baguette defines it.

A node is a string or ``{"t": tag, "a": attrs, "c": children}``, attribute
values are strings, and a patch is a list of ``replace``, ``attrs`` and
``splice`` operations whose ``at`` is a path of child indices.
"""

import copy
from typing import Protocol


class Host(Protocol):
    def render(self, window: int, frame: dict) -> None: ...
    def close(self, window: int) -> None: ...


def apply(tree, patch):
    """Applies `patch` to `tree`, as the host does, returning a new tree."""
    tree = copy.deepcopy(tree)
    for op in patch:
        tree = _update(tree, op["at"], lambda node, op=op: _change(node, op))
    return tree


def _change(node, op):
    match op["op"]:
        case "replace":
            return copy.deepcopy(op["node"])
        case "attrs":
            return {**node, "a": dict(op["a"])}
        case "splice":
            c, start = node["c"], op["start"]
            added = copy.deepcopy(op["c"])
            return {**node, "c": c[:start] + added + c[start + op["delete"] :]}
    raise ValueError(f"unknown patch op {op['op']!r}")


def _update(node, at, fun):
    if not at:
        return fun(node)
    i, *rest = at
    children = list(node["c"])
    children[i] = _update(children[i], rest, fun)
    return {**node, "c": children}

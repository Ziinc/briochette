"""Widgets render to baguette's element vocabulary, and setters patch only their node."""

import pytest

from briochette.core import Qt
from briochette.widgets import QWidget, QVBoxLayout, QLabel, QPushButton


def counter():
    window = QWidget()
    window.label = QLabel("Count: 0")
    window.button = QPushButton("+")
    window.button.setAccessibleName("Increment")
    layout = QVBoxLayout(window)
    layout.addWidget(window.label)
    layout.addWidget(window.button)
    return window


def test_counter_tree(qtbot):
    window = counter()
    qtbot.addWidget(window)
    assert qtbot.host.tree(window.winId()) == {
        "t": "div",
        "a": {"class": "size-full flex-col"},
        "c": [
            {"t": "text", "a": {}, "c": ["Count: 0"]},
            {
                "t": "button",
                "a": {"aria-label": "Increment", "phx-click": window.button._id},
                "c": ["+"],
            },
        ],
    }


def test_set_text_replaces_only_the_text(qtbot):
    window = counter()
    qtbot.addWidget(window)
    window.label.setText("Count: 1")
    qtbot.wait(0)
    assert qtbot.host.frames(window.winId())[-1] == {
        "patch": [{"op": "replace", "at": [0, 0], "node": "Count: 1"}]
    }


def test_setters_in_one_step_go_out_as_one_frame(qtbot):
    window = counter()
    qtbot.addWidget(window)
    window.label.setText("a")
    window.button.setAccessibleName("Add")
    qtbot.wait(0)
    assert qtbot.host.frames(window.winId())[-1] == {
        "patch": [
            {"op": "replace", "at": [0, 0], "node": "a"},
            {"op": "attrs", "at": [1], "a": {"aria-label": "Add", "phx-click": window.button._id}},
        ]
    }


def test_add_widget_after_show_splices(qtbot):
    window = counter()
    qtbot.addWidget(window)
    window.layout().addWidget(QLabel("new"))
    qtbot.wait(0)
    assert qtbot.host.frames(window.winId())[-1] == {
        "patch": [
            {"op": "splice", "at": [], "start": 2, "delete": 0, "c": [{"t": "text", "a": {}, "c": ["new"]}]}
        ]
    }


def test_click_without_a_handler_fails(qtbot):
    label = QLabel("x")
    qtbot.addWidget(label)
    with pytest.raises(AssertionError, match="does not handle clicks"):
        qtbot.mouseClick(label, Qt.MouseButton.LeftButton)


def test_patched_tree_matches_a_fresh_render(qtbot):
    window = counter()
    qtbot.addWidget(window)
    window.label.setText("")
    window.label.setText("back")
    window.button.setAccessibleName("Add")
    window.layout().addWidget(QPushButton("more"))
    qtbot.wait(0)
    assert qtbot.host.tree(window.winId()) == window._node()

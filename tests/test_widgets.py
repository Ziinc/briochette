"""The M2 widget subset: nodes in baguette's vocabulary, setters as patches."""

import pytest

from briochette.core import Qt
from briochette.widgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def window_with(*widgets, layout=QVBoxLayout):
    window = QWidget()
    box = layout(window)
    for w in widgets:
        box.addWidget(w)
    return window


def shown(qtbot, *widgets, layout=QVBoxLayout):
    window = window_with(*widgets, layout=layout)
    qtbot.addWidget(window)
    return window


def tree(qtbot, window):
    qtbot.wait(0)
    return qtbot.host.tree(window.winId())


def last_patch(qtbot, window):
    qtbot.wait(0)
    return qtbot.host.frames(window.winId())[-1]["patch"]


# Layouts


def test_hbox_is_a_flex_row(qtbot):
    window = shown(qtbot, QLabel("a"), layout=QHBoxLayout)
    assert tree(qtbot, window)["a"]["class"] == "size-full flex-row"


def test_spacing_and_margins_become_classes(qtbot):
    window = shown(qtbot, QLabel("a"))
    window.layout().setSpacing(6)
    window.layout().setContentsMargins(1, 2, 3, 4)
    assert tree(qtbot, window)["a"]["class"] == (
        "size-full flex-col gap-[6px] pl-[1px] pt-[2px] pr-[3px] pb-[4px]"
    )


def test_stretch_grows_the_widget_and_add_stretch_adds_a_spacer(qtbot):
    window = QWidget()
    box = QHBoxLayout(window)
    box.addWidget(QLabel("a"), 1)
    box.addStretch()
    qtbot.addWidget(window)
    children = tree(qtbot, window)["c"]
    assert children[0]["a"]["class"] == "flex-1"
    assert children[1] == {"t": "div", "a": {"class": "flex-1"}, "c": []}


def test_nested_layout_gets_a_box_of_its_own(qtbot):
    window = QWidget()
    outer = QVBoxLayout(window)
    row = QHBoxLayout()
    row.addWidget(QLabel("a"))
    outer.addLayout(row)
    qtbot.addWidget(window)
    assert tree(qtbot, window)["c"][0] == {
        "t": "div",
        "a": {"class": "flex-row"},
        "c": [{"t": "text", "a": {}, "c": ["a"]}],
    }


def test_grid_is_rows_of_cells(qtbot):
    window = QWidget()
    grid = QGridLayout(window)
    a, b, c = QLabel("a"), QLabel("b"), QLabel("c")
    grid.addWidget(a, 0, 0)
    grid.addWidget(b, 0, 1)
    grid.addWidget(c, 1, 1)
    qtbot.addWidget(window)
    rows = tree(qtbot, window)["c"]
    assert [[cell["c"] for cell in row["c"]] for row in rows] == [
        [[{"t": "text", "a": {}, "c": ["a"]}], [{"t": "text", "a": {}, "c": ["b"]}]],
        [[], [{"t": "text", "a": {}, "c": ["c"]}]],
    ]
    assert rows[0]["a"]["class"] == "flex-row"
    assert rows[0]["c"][0]["a"]["class"] == "flex-1"
    c.setText("C")
    assert tree(qtbot, window)["c"][1]["c"][1]["c"][0]["c"] == ["C"]


# Enabled and visible


def test_set_enabled_toggles_disabled(qtbot):
    button = QPushButton("go")
    window = shown(qtbot, button)
    button.setEnabled(False)
    assert not button.isEnabled()
    assert tree(qtbot, window)["c"][0]["a"]["disabled"] == ""
    button.setEnabled(True)
    assert "disabled" not in tree(qtbot, window)["c"][0]["a"]


def test_hidden_widget_is_a_placeholder(qtbot):
    label = QLabel("a")
    window = shown(qtbot, label)
    label.hide()
    assert not label.isVisible()
    assert tree(qtbot, window)["c"][0] == {"t": "div", "a": {"class": "hidden"}, "c": []}
    label.show()
    assert tree(qtbot, window)["c"][0] == {"t": "text", "a": {}, "c": ["a"]}


def test_disabled_button_cannot_be_clicked(qtbot):
    button, got = QPushButton("go"), []
    button.clicked.connect(lambda: got.append(1))
    shown(qtbot, button)
    button.setEnabled(False)
    with pytest.raises(AssertionError, match="disabled"):
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert got == []


# QLineEdit


def test_line_edit_node(qtbot):
    edit = QLineEdit("hi")
    edit.setPlaceholderText("Title")
    window = shown(qtbot, edit)
    assert tree(qtbot, window)["c"][0] == {
        "t": "form",
        "a": {"phx-submit": edit._id},
        "c": [
            {
                "t": "input",
                "a": {"name": "value", "phx-change": edit._id, "placeholder": "Title", "value": "hi"},
                "c": [],
            }
        ],
    }


def test_typing_emits_text_changed_and_edited(qtbot):
    edit, changed, edited = QLineEdit(), [], []
    edit.textChanged.connect(changed.append)
    edit.textEdited.connect(edited.append)
    shown(qtbot, edit)
    qtbot.keyClicks(edit, "ab")
    assert edit.text() == "ab"
    assert changed == edited == ["ab"]


def test_set_text_patches_the_value_and_emits_only_text_changed(qtbot):
    edit, changed, edited = QLineEdit(), [], []
    edit.textChanged.connect(changed.append)
    edit.textEdited.connect(edited.append)
    window = shown(qtbot, edit)
    edit.setText("x")
    assert last_patch(qtbot, window) == [
        {"op": "attrs", "at": [0, 0], "a": {"name": "value", "phx-change": edit._id, "value": "x"}}
    ]
    assert (changed, edited) == (["x"], [])


def test_enter_emits_return_pressed(qtbot):
    edit, got = QLineEdit(), []
    edit.returnPressed.connect(lambda: got.append(edit.text()))
    shown(qtbot, edit)
    qtbot.keyClicks(edit, "milk")
    qtbot.keyClick(edit, Qt.Key.Key_Return)
    assert got == ["milk"]


# QCheckBox


def test_check_box_node_and_click(qtbot):
    box, toggled, states = QCheckBox("Done"), [], []
    box.toggled.connect(toggled.append)
    box.stateChanged.connect(states.append)
    window = shown(qtbot, box)
    assert tree(qtbot, window)["c"][0] == {
        "t": "div",
        "a": {"class": "flex-row items-center gap-2"},
        "c": [
            {"t": "input", "a": {"aria-label": "Done", "phx-click": box._id, "type": "checkbox"}, "c": []},
            {"t": "text", "a": {}, "c": ["Done"]},
        ],
    }
    qtbot.mouseClick(box, Qt.MouseButton.LeftButton)
    assert box.isChecked()
    assert (toggled, states) == ([True], [2])
    assert tree(qtbot, window)["c"][0]["c"][0]["a"]["checked"] == ""
    qtbot.mouseClick(box, Qt.MouseButton.LeftButton)
    assert (toggled, states) == ([True, False], [2, 0])


def test_set_checked_without_change_emits_nothing(qtbot):
    box, toggled = QCheckBox("x"), []
    box.toggled.connect(toggled.append)
    box.setChecked(False)
    box.setChecked(True)
    box.setChecked(True)
    assert toggled == [True]


# QProgressBar


def test_progress_bar(qtbot):
    bar = QProgressBar()
    bar.setRange(0, 200)
    bar.setValue(50)
    window = shown(qtbot, bar)
    assert tree(qtbot, window)["c"][0] == {
        "t": "div",
        "a": {
            "aria-valuemax": "200",
            "aria-valuemin": "0",
            "aria-valuenow": "50",
            "class": "h-2 w-full rounded-full bg-muted overflow-hidden",
            "role": "progressbar",
        },
        "c": [{"t": "div", "a": {"class": "h-full bg-primary w-[25%]"}, "c": []}],
    }
    got = []
    bar.valueChanged.connect(got.append)
    bar.setValue(500)
    assert (bar.value(), got) == (200, [200])


def test_patched_tree_matches_a_fresh_render(qtbot):
    edit, box, bar, label, button = QLineEdit(), QCheckBox("a"), QProgressBar(), QLabel("x"), QPushButton("b")
    window = QWidget()
    outer = QVBoxLayout(window)
    for w in (edit, box, bar):
        outer.addWidget(w)
    grid = QGridLayout()
    grid.addWidget(label, 0, 0)
    outer.addLayout(grid)
    qtbot.addWidget(window)
    edit.setText("t")
    edit.setPlaceholderText("p")
    edit.setEnabled(False)
    box.setChecked(True)
    box.setText("b")
    bar.setValue(40)
    label.hide()
    label.setText("y")
    label.show()
    grid.addWidget(button, 1, 1)
    button.setEnabled(False)
    outer.setSpacing(4)
    outer.addStretch()
    assert tree(qtbot, window) == window._node()


def test_remove_widget_splices_it_out(qtbot):
    a, b = QLabel("a"), QLabel("b")
    window = shown(qtbot, a, b)
    window.layout().removeWidget(a)
    assert last_patch(qtbot, window) == [{"op": "splice", "at": [], "start": 0, "delete": 1, "c": []}]
    assert a.parent() is None and window.layout().count() == 1


def test_delete_later_takes_it_out_of_its_layout(qtbot):
    a, b = QPushButton("a"), QLabel("b")
    window = shown(qtbot, a, b)
    a.deleteLater()
    assert tree(qtbot, window)["c"] == [{"t": "text", "a": {}, "c": ["b"]}]

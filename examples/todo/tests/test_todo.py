from briochette.core import Qt
from todo.app import Todo


def add(qtbot, window, text):
    qtbot.keyClicks(window.input, text)
    qtbot.keyClick(window.input, Qt.Key.Key_Return)


def test_add_check_and_delete(qtbot):
    window = Todo()
    qtbot.addWidget(window)
    add(qtbot, window, "Buy milk")
    add(qtbot, window, "Feed cat")
    assert window.input.text() == ""
    assert window.left.text() == "2 of 2 left"

    qtbot.mouseClick(window.rows[0].done, Qt.MouseButton.LeftButton)
    assert window.left.text() == "1 of 2 left"

    qtbot.mouseClick(window.rows[0].delete, Qt.MouseButton.LeftButton)
    assert [row.done.text() for row in window.rows] == ["Feed cat"]
    assert window.left.text() == "1 of 1 left"


def test_blank_todo_is_not_added(qtbot):
    window = Todo()
    qtbot.addWidget(window)
    qtbot.mouseClick(window.add, Qt.MouseButton.LeftButton)
    assert window.rows == []

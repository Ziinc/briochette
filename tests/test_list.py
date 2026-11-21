"""QListView over a model: a virtualized <list>, rows fetched by range."""

from briochette.core import QAbstractListModel, QModelIndex, QStringListModel, Qt
from briochette.widgets import QLabel, QListView, QVBoxLayout, QWidget


def shown(qtbot, view):
    window = QWidget()
    layout = QVBoxLayout(window)
    layout.addWidget(QLabel("title"))
    layout.addWidget(view)
    qtbot.addWidget(window)
    return window


def test_list_node_carries_count_and_rows_event(qtbot):
    view = QListView()
    view.setModel(QStringListModel(["a", "b", "c"]))
    window = shown(qtbot, view)
    qtbot.wait(0)
    assert qtbot.host.tree(window.winId())["c"][1] == {
        "t": "list",
        "a": {"class": "flex-1", "id": view._id, "phx-rows": view._id, "rows": "3"},
        "c": [],
    }


def test_rows_are_sent_when_the_host_asks(qtbot):
    view = QListView()
    view.setModel(QStringListModel([f"item {i}" for i in range(100)]))
    window = shown(qtbot, view)
    qtbot.showRows(view, 10, 13)
    rows = qtbot.host.rows(window.winId(), view._id)
    assert sorted(rows) == [10, 11, 12]
    assert rows[10] == {
        "t": "div",
        "a": {"class": "px-2 py-1", "phx-click": view._id, "phx-value-row": "10", "role": "option"},
        "c": ["item 10"],
    }


def test_every_frame_carries_the_visible_rows(qtbot):
    view = QListView()
    view.setModel(QStringListModel(["a", "b"]))
    window = shown(qtbot, view)
    qtbot.showRows(view, 0, 2)
    window.layout().itemAt(0).widget().setText("new title")
    qtbot.wait(0)
    frame = qtbot.host.frames(window.winId())[-1]
    assert frame["lists"] == {view._id: {"id": view._id, "start": 0, "rows": [view._row(0), view._row(1)]}}
    assert sorted(qtbot.host.rows(window.winId(), view._id)) == [0, 1]


def test_model_changes_update_count_and_rows(qtbot):
    model = QStringListModel(["a", "b"])
    view = QListView()
    view.setModel(model)
    window = shown(qtbot, view)
    qtbot.showRows(view, 0, 2)
    model.insertRows(2, 1)
    model.setData(model.index(2), "c")
    model.setData(model.index(0), "A")
    qtbot.wait(0)
    assert qtbot.host.tree(window.winId())["c"][1]["a"]["rows"] == "3"
    rows = qtbot.host.rows(window.winId(), view._id)
    assert rows[0]["c"] == ["A"]


def test_click_selects_and_emits_the_index(qtbot):
    view, clicked = QListView(), []
    view.setModel(QStringListModel(["a", "b", "c"]))
    view.clicked.connect(lambda index: clicked.append(index.row()))
    window = shown(qtbot, view)
    qtbot.clickRow(view, 1)
    assert clicked == [1]
    assert view.currentIndex().row() == 1
    row = qtbot.host.rows(window.winId(), view._id)[1]
    assert row["a"]["aria-selected"] == "true"


class Squares(QAbstractListModel):
    def rowCount(self, parent=QModelIndex()):
        return 5

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return str(index.row() ** 2)


def test_custom_model(qtbot):
    view = QListView()
    view.setModel(Squares())
    window = shown(qtbot, view)
    qtbot.showRows(view, 0, 5)
    rows = qtbot.host.rows(window.winId(), view._id)
    assert [rows[i]["c"] for i in range(5)] == [["0"], ["1"], ["4"], ["9"], ["16"]]

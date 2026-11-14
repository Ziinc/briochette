from briochette.core import Qt
from gallery.app import Gallery


def test_jobs_list_is_long_and_rows_come_on_demand(qtbot):
    window = Gallery()
    qtbot.addWidget(window)
    assert window.jobs.model().rowCount() == 10_000
    qtbot.showRows(window.jobs, 5000, 5003)
    rows = qtbot.host.rows(window.winId(), window.jobs._id)
    assert rows[5001]["c"] == ["Job 5001"]


def test_choosing_a_job(qtbot):
    window = Gallery()
    qtbot.addWidget(window)
    qtbot.clickRow(window.jobs, 3)
    assert window.chosen.text() == "Chose Job 3"


def test_more_advances_progress(qtbot):
    window = Gallery()
    qtbot.addWidget(window)
    qtbot.mouseClick(window.more, Qt.MouseButton.LeftButton)
    assert window.progress.value() == 50
    assert window.done.text() == "50% uploaded"


def test_copy_then_paste(qtbot):
    window = Gallery()
    qtbot.addWidget(window)
    qtbot.mouseClick(window.copy, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.paste, Qt.MouseButton.LeftButton)
    assert window.pasted.text() == "Pasted: 40% uploaded"


def test_rename_sets_the_window_title(qtbot):
    window = Gallery()
    qtbot.addWidget(window)
    qtbot.mouseClick(window.rename, Qt.MouseButton.LeftButton)
    assert window.windowTitle() == "Renamed"
    assert qtbot.host.calls[-1]["call"] == "window.set_title"


def test_escape_resets_progress(qtbot):
    window = Gallery()
    qtbot.addWidget(window)
    qtbot.mouseClick(window.more, Qt.MouseButton.LeftButton)
    qtbot.keyClick(window, Qt.Key.Key_Escape)
    assert window.progress.value() == 40

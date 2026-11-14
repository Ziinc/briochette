"""briochette's widgets on one screen, after baguette's gallery."""

from briochette.core import QAbstractListModel, QModelIndex, Qt
from briochette.gui import QKeySequence, QShortcut
from briochette.widgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListView,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class Jobs(QAbstractListModel):
    def rowCount(self, parent=QModelIndex()):
        return 10_000

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return f"Job {index.row()}"


class Gallery(QWidget):
    def __init__(self):
        super().__init__()
        self.progress = QProgressBar()
        self.progress.setAccessibleName("Upload")
        self.progress.setValue(40)
        self.done = QLabel()
        self.more = QPushButton("More")
        self.more.clicked.connect(lambda: self.progress.setValue(self.progress.value() + 10))
        self.progress.valueChanged.connect(self.show_done)

        self.copy = QPushButton("Copy")
        self.copy.clicked.connect(lambda: QApplication.clipboard().setText(self.done.text()))
        self.paste = QPushButton("Paste")
        self.paste.clicked.connect(
            lambda: self.pasted.setText(f"Pasted: {QApplication.clipboard().text()}")
        )
        self.rename = QPushButton("Rename")
        self.rename.clicked.connect(lambda: self.setWindowTitle("Renamed"))
        self.pasted = QLabel("Pasted: ")

        self.jobs = QListView()
        self.jobs.setModel(Jobs(self))
        self.jobs.clicked.connect(lambda index: self.chosen.setText(f"Chose {index.data()}"))
        self.chosen = QLabel("Chose nothing")

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        for button in (self.copy, self.paste, self.rename):
            buttons.addWidget(button)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(self.progress)
        layout.addWidget(self.done)
        layout.addWidget(self.more)
        layout.addLayout(buttons)
        layout.addWidget(self.pasted)
        layout.addWidget(self.jobs, 1)
        layout.addWidget(self.chosen)
        QShortcut(QKeySequence("Esc"), self, activated=lambda: self.progress.setValue(40))
        self.show_done()

    def show_done(self):
        self.done.setText(f"{self.progress.value()}% uploaded")


def main():
    app = QApplication([])
    window = Gallery()
    window.show()
    app.exec()

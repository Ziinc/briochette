from briochette.widgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class Row(QWidget):
    def __init__(self, text):
        super().__init__()
        self.done = QCheckBox(text)
        self.delete = QPushButton("Delete")
        self.delete.setAccessibleName(f"Delete {text}")
        layout = QHBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(self.done, 1)
        layout.addWidget(self.delete)


class Todo(QWidget):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.input = QLineEdit()
        self.input.setPlaceholderText("What needs doing?")
        self.input.setAccessibleName("New todo")
        self.input.returnPressed.connect(self.add_todo)
        self.add = QPushButton("Add")
        self.add.clicked.connect(self.add_todo)
        self.left = QLabel()

        entry = QHBoxLayout()
        entry.setSpacing(8)
        entry.addWidget(self.input, 1)
        entry.addWidget(self.add)
        self.list = QVBoxLayout()
        self.list.setSpacing(4)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addLayout(entry)
        layout.addLayout(self.list)
        layout.addStretch()
        layout.addWidget(self.left)
        self.update_left()

    def add_todo(self):
        text = self.input.text().strip()
        if not text:
            return
        row = Row(text)
        row.done.toggled.connect(self.update_left)
        row.delete.clicked.connect(lambda: self.remove(row))
        self.rows.append(row)
        self.list.addWidget(row)
        self.input.clear()
        self.update_left()

    def remove(self, row):
        self.rows.remove(row)
        row.deleteLater()
        self.update_left()

    def update_left(self):
        left = sum(not row.done.isChecked() for row in self.rows)
        self.left.setText(f"{left} of {len(self.rows)} left")


def main():
    app = QApplication([])
    window = Todo()
    window.show()
    app.exec()

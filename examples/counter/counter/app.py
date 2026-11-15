from briochette.gui import QKeySequence, QShortcut
from briochette.widgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton


class Counter(QWidget):
    def __init__(self):
        super().__init__()
        self.count = 0
        self.label = QLabel("Count: 0")
        self.increment = QPushButton("+")
        self.increment.setAccessibleName("Increment")
        self.increment.clicked.connect(self.inc)
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addWidget(self.increment)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.reset)

    def inc(self):
        self.count += 1
        self.label.setText(f"Count: {self.count}")
        # The phone smoke tests read this from the device log.
        print(f"counter: count={self.count}", flush=True)

    def reset(self):
        self.count = 0
        self.label.setText("Count: 0")


def main():
    app = QApplication([])
    window = Counter()
    window.show()
    app.exec()

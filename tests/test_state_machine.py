"""Random widget operations; after each, the host's patched tree must equal a
fresh render of the widgets (the oracle gpui-proptest uses)."""

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from briochette.testing import HeadlessHost
from briochette.widgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

text = st.text(alphabet="ab ", max_size=3)
KINDS = [QLabel, QPushButton, QLineEdit, QCheckBox, QProgressBar]


class Widgets(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.app = QApplication.instance()
        self.host = self.app._host
        self.window = QWidget()
        self.boxes = [QVBoxLayout(self.window)]
        self.widgets = []
        self.window.show()

    def teardown(self):
        self.window.close()

    @rule(kind=st.sampled_from(KINDS), box=st.integers(0, 10), stretch=st.booleans())
    def add(self, kind, box, stretch):
        widget = kind()
        self.boxes[box % len(self.boxes)].addWidget(widget, 1 if stretch else 0)
        self.widgets.append(widget)

    @rule(box=st.integers(0, 10))
    def add_box(self, box):
        layout = QHBoxLayout()
        self.boxes[box % len(self.boxes)].addLayout(layout)
        self.boxes.append(layout)

    @precondition(lambda self: self.widgets)
    @rule(i=st.integers(0, 100))
    def remove(self, i):
        widget = self.widgets.pop(i % len(self.widgets))
        widget.deleteLater()

    @precondition(lambda self: self.widgets)
    @rule(i=st.integers(0, 100), value=text)
    def set_text(self, i, value):
        widget = self.widgets[i % len(self.widgets)]
        if hasattr(widget, "setText"):
            widget.setText(value)

    @precondition(lambda self: self.widgets)
    @rule(i=st.integers(0, 100), on=st.booleans())
    def toggle(self, i, on):
        widget = self.widgets[i % len(self.widgets)]
        widget.setEnabled(on)
        if isinstance(widget, QCheckBox):
            widget.setChecked(not on)
        if isinstance(widget, QProgressBar):
            widget.setValue(30 if on else 70)

    @precondition(lambda self: self.widgets)
    @rule(i=st.integers(0, 100), visible=st.booleans())
    def visibility(self, i, visible):
        self.widgets[i % len(self.widgets)].setVisible(visible)

    @rule(box=st.integers(0, 10), n=st.integers(0, 12))
    def spacing(self, box, n):
        self.boxes[box % len(self.boxes)].setSpacing(n)

    @invariant()
    def host_tree_is_a_fresh_render(self):
        self.app.flush()
        assert self.host.tree(self.window.winId()) == self.window._node()


def test_widgets_state_machine(qapp):
    assert isinstance(qapp._host, HeadlessHost)
    Widgets.TestCase.settings = settings(max_examples=60, stateful_step_count=30, deadline=None)
    Widgets.TestCase().runTest()

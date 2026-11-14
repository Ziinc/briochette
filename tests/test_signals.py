from briochette.core import QObject, pyqtSignal


class Source(QObject):
    changed = pyqtSignal(int)


def test_emit_reaches_every_slot_in_order():
    source, got = Source(), []
    source.changed.connect(lambda n: got.append(("a", n)))
    source.changed.connect(lambda n: got.append(("b", n)))
    source.changed.emit(3)
    assert got == [("a", 3), ("b", 3)]


def test_slot_may_take_fewer_arguments():
    source, got = Source(), []
    source.changed.connect(lambda: got.append("called"))
    source.changed.emit(3)
    assert got == ["called"]


def test_signals_are_per_instance():
    a, b, got = Source(), Source(), []
    a.changed.connect(got.append)
    b.changed.emit(1)
    assert got == []


def test_disconnect():
    source, got = Source(), []
    source.changed.connect(got.append)
    source.changed.disconnect(got.append)
    source.changed.emit(1)
    assert got == []

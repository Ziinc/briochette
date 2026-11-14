"""Applies every case of the shared patches.json the way the host does."""

import json
from pathlib import Path

import pytest

from briochette._wire import apply

CASES = json.loads((Path(__file__).parent / "fixtures" / "patches.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_apply(case):
    assert apply(case["old"], case["patch"]) == case["new"]

#!/usr/bin/env python3
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("bench_dashboard.py")
SPEC = importlib.util.spec_from_file_location("bench_dashboard", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_dashboard_defaults_to_current_checkout_and_generic_cells():
    assert MODULE.LOGS == SCRIPT.parent.parent / "logs"
    assert MODULE.CELL_GLOB == "p[1-3]_*_v*"

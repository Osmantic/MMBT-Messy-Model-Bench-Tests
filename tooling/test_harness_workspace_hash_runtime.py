#!/usr/bin/env python3
import importlib.util
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).with_name("harness.py")
if not SCRIPT.exists():
    SCRIPT = Path(__file__).parents[1] / "mmbt-qwen38-eaaa8ca" / "tooling" / "harness.py"
SPEC = importlib.util.spec_from_file_location("mmbt_harness_workspace_hash", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_workspace_hash_ignores_only_known_test_runtime_churn(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(stdout="abc123\n")

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)
    assert MODULE.workspace_state_hash() == "abc123"

    command = captured["command"]
    assert command[:4] == ["docker", "exec", MODULE.SANDBOX, "bash"]
    shell = command[-1]
    assert "*/.git/objects" in shell
    assert "*/__pycache__" in shell
    assert "*/.pytest_cache" in shell
    assert "*.pyc" in shell
    assert ".coverage.*" in shell
    assert "-print0" in shell
    assert "sort -z" in shell
    assert "xargs -0" in shell
    assert captured["kwargs"] == {
        "capture_output": True,
        "text": True,
        "timeout": 30,
    }

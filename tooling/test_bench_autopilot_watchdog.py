#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).with_name("bench_autopilot.py")
if not SCRIPT.exists():
    SCRIPT = Path(__file__).with_name("mmbt-bench_autopilot.py")
SPEC = importlib.util.spec_from_file_location("bench_autopilot_watchdog", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _write_row(path: Path, row: dict):
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_pending_tool_uses_long_tool_watchdog(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    _write_row(
        transcript,
        {"type": "model", "finish_reason": "tool_calls", "tool_calls": [{"name": "bash"}]},
    )
    assert MODULE.watchdog_stuck_policy(
        {"stuck_secs": 1200, "tool_stuck_secs": 3900}, transcript
    ) == (3900, "pending-tool")


def test_completed_tool_returns_to_short_watchdog(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "model", "finish_reason": "tool_calls"})
        + "\n"
        + json.dumps({"type": "tool", "name": "bash", "wall_s": 1800.1})
        + "\n",
        encoding="utf-8",
    )
    assert MODULE.watchdog_stuck_policy(
        {"stuck_secs": 1200, "tool_stuck_secs": 3900}, transcript
    ) == (1200, "inference-or-idle")


def test_pending_tool_limit_never_shortens_base_limit(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    _write_row(transcript, {"type": "model", "finish_reason": "tool_calls"})
    assert MODULE.watchdog_stuck_policy(
        {"stuck_secs": 5000, "tool_stuck_secs": 3900}, transcript
    ) == (5000, "pending-tool")


def test_bad_or_missing_transcript_fails_closed_to_base_limit(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("not-json\n", encoding="utf-8")
    assert MODULE.watchdog_stuck_policy({"stuck_secs": 1200}, transcript) == (
        1200,
        "inference-or-idle",
    )


def test_operator_stopped_research_loop_is_terminal_with_evidence(tmp_path):
    old_logs = MODULE.LOGS
    try:
        MODULE.LOGS = tmp_path
        run = tmp_path / "p1_testwrite_model_v1"
        run.mkdir()
        (run / "receipt.json").write_text("{}\n", encoding="utf-8")
        (run / "transcript.jsonl").write_text("{}\n", encoding="utf-8")
        (run / "label.json").write_text(
            json.dumps({"primary": "stuck-in-research"}) + "\n",
            encoding="utf-8",
        )
        assert MODULE.cell_done(run.name)
    finally:
        MODULE.LOGS = old_logs


def test_unapproved_operator_label_is_not_terminal(tmp_path):
    old_logs = MODULE.LOGS
    try:
        MODULE.LOGS = tmp_path
        run = tmp_path / "p1_testwrite_model_v1"
        run.mkdir()
        (run / "receipt.json").write_text("{}\n", encoding="utf-8")
        (run / "transcript.jsonl").write_text("{}\n", encoding="utf-8")
        (run / "label.json").write_text(
            json.dumps({"primary": "harness-fault"}) + "\n",
            encoding="utf-8",
        )
        assert not MODULE.cell_done(run.name)
    finally:
        MODULE.LOGS = old_logs

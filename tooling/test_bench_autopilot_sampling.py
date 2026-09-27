#!/usr/bin/env python3
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("bench_autopilot.py")
SPEC = importlib.util.spec_from_file_location("bench_autopilot", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_model_card_sampling_reaches_child_environment():
    env = MODULE.benchmark_environment(
        {
            "benchmark_temperature": 1.0,
            "benchmark_top_p": 0.95,
            "benchmark_top_k": 64,
            "benchmark_max_output_tokens_cap": 262144,
            "serving_manifest": "/tmp/serving.json",
        },
        {"PRESERVED": "yes", "BENCH_TOP_K": "stale"},
    )
    assert env["PRESERVED"] == "yes"
    assert env["BENCH_TEMP"] == "1.0"
    assert env["BENCH_TOP_P"] == "0.95"
    assert env["BENCH_TOP_K"] == "64"
    assert env["BENCH_MAX_OUTPUT_TOKENS_CAP"] == "262144"
    assert env["BENCH_SERVING_MANIFEST"] == "/tmp/serving.json"


def test_unset_sampling_does_not_leak_parent_overrides():
    env = MODULE.benchmark_environment(
        {},
        {
            "PRESERVED": "yes",
            "BENCH_TEMP": "9",
            "BENCH_TOP_P": "0.1",
            "BENCH_TOP_K": "1",
            "BENCH_MAX_OUTPUT_TOKENS_CAP": "123",
            "BENCH_SERVING_MANIFEST": "/tmp/stale.json",
        },
    )
    assert env == {"PRESERVED": "yes"}


def test_arm_sampling_overrides_global_without_losing_fallbacks():
    env = MODULE.benchmark_environment(
        {
            "benchmark_temperature": 1.0,
            "benchmark_top_p": 0.95,
            "benchmark_top_k": 20,
            "benchmark_min_p": 0.0,
            "benchmark_presence_penalty": 0.0,
            "benchmark_repeat_penalty": 1.0,
            "benchmark_seed": 42,
            "benchmark_sandbox_gpus": "none",
            "preserve_thinking": True,
        },
        {"PRESERVED": "yes"},
        arm={
            "benchmark_temperature": 0.7,
            "benchmark_top_p": 0.8,
            "benchmark_presence_penalty": 1.5,
            "preserve_thinking": False,
            "reasoning_effort_location": "top_level",
        },
    )
    assert env["PRESERVED"] == "yes"
    assert env["BENCH_TEMP"] == "0.7"
    assert env["BENCH_TOP_P"] == "0.8"
    assert env["BENCH_TOP_K"] == "20"
    assert env["BENCH_MIN_P"] == "0.0"
    assert env["BENCH_PRESENCE_PENALTY"] == "1.5"
    assert env["BENCH_REPEAT_PENALTY"] == "1.0"
    assert env["BENCH_SEED"] == "42"
    assert env["BENCH_SANDBOX_GPUS"] == "none"
    assert env["BENCH_PRESERVE_THINKING"] == "false"
    assert env["BENCH_REASONING_EFFORT_LOCATION"] == "top_level"


def test_configured_ports_are_ordered_and_deduplicated():
    assert MODULE.configured_ports({"port": 8000}) == [8000]
    assert MODULE.configured_ports({"port": 8000, "lane_ports": [8000, "8001", 8000]}) == [8000, 8001]


def test_slot_progress_signature_tracks_only_live_decode_progress():
    payload = [
        {
            "id": 0,
            "id_task": 10,
            "is_processing": False,
            "n_prompt_tokens_processed": 100,
            "next_token": [{"n_decoded": 20, "n_remain": 1000}],
        },
        {
            "id": 3,
            "id_task": 99,
            "is_processing": True,
            "n_prompt_tokens_processed": 67,
            "next_token": [{"n_decoded": 16296, "n_remain": 213539}],
        },
    ]
    assert MODULE.slot_progress_signature(payload) == ((3, 99, 67, 16296, 213539),)
    payload[1]["next_token"][0]["n_decoded"] += 1
    assert MODULE.slot_progress_signature(payload) == ((3, 99, 67, 16297, 213539),)


def test_slot_progress_signature_is_empty_for_idle_or_bad_payload():
    assert MODULE.slot_progress_signature([]) == ()
    assert MODULE.slot_progress_signature({"not": "a slot list"}) == ()
    assert MODULE.slot_progress_signature([{"id": 0, "is_processing": False}]) == ()


def test_substance_targets_include_both_live_lanes(tmp_path):
    old_logs = MODULE.LOGS
    old_active = MODULE.active_harnesses_by_port
    try:
        MODULE.LOGS = tmp_path
        for cell in ("p1_refactor_model_v3", "p3_market_model_v1"):
            (tmp_path / cell).mkdir()
            (tmp_path / cell / "transcript.jsonl").write_text("{}\n")
        MODULE.active_harnesses_by_port = lambda: {
            8000: {"pid": 101, "cell": "p1_refactor_model_v3"},
            8001: {"pid": 202, "cell": "p3_market_model_v1"},
        }
        targets = MODULE.active_substance_targets({"port": 8000, "lane_ports": [8000, 8001]})
        assert [(target["port"], target["pid"], target["cell"]) for target in targets] == [
            (8000, 101, "p1_refactor_model_v3"),
            (8001, 202, "p3_market_model_v1"),
        ]
    finally:
        MODULE.LOGS = old_logs
        MODULE.active_harnesses_by_port = old_active

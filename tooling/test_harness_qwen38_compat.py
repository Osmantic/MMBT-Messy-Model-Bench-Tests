#!/usr/bin/env python3
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("harness.py")
SPEC = importlib.util.spec_from_file_location("mmbt_harness", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_qwen38_thinking_payload_uses_top_level_xhigh_and_full_sampling():
    payload = MODULE.build_chat_payload(
        "Qwen3.8-27B-UD-Q4_K_XL",
        [{"role": "user", "content": "test"}],
        262144,
        temperature=1.0,
        top_p=0.95,
        top_k=20,
        min_p=0.0,
        presence_penalty=0.0,
        repeat_penalty=1.0,
        seed=42,
        reasoning_effort="xhigh",
        reasoning_effort_location="top_level",
        enable_thinking=True,
        preserve_thinking=True,
    )
    assert payload["reasoning_effort"] == "xhigh"
    assert payload["chat_template_kwargs"] == {
        "enable_thinking": True,
        "preserve_thinking": True,
    }
    assert payload["temperature"] == 1.0
    assert payload["top_p"] == 0.95
    assert payload["top_k"] == 20
    assert payload["min_p"] == 0.0
    assert payload["presence_penalty"] == 0.0
    assert payload["repeat_penalty"] == 1.0
    assert payload["seed"] == 42


def test_legacy_reasoning_effort_location_remains_backwards_compatible():
    payload = MODULE.build_chat_payload(
        "step3p7", [], 1000,
        reasoning_effort="high",
        reasoning_effort_location="chat_template_kwargs",
    )
    assert "reasoning_effort" not in {k: v for k, v in payload.items()
                                       if k != "chat_template_kwargs"}
    assert payload["chat_template_kwargs"]["reasoning_effort"] == "high"


def test_remote_lane_provenance_matches_coordinator_tunnel_port():
    manifest = {
        "topology": {
            "lanes": [
                {
                    "lane_index": 0,
                    "coordinator_port": 18101,
                    "inference_host": "Tower1",
                    "gpu_uuid": "GPU-tower1",
                },
                {
                    "lane_index": 1,
                    "coordinator_port": 18103,
                    "inference_host": "Tower3",
                    "gpu_uuid": "GPU-tower3",
                },
            ]
        }
    }
    provenance = MODULE._manifest_lane_provenance(
        manifest, "http://127.0.0.1:18103/v1/chat/completions"
    )
    assert provenance["matched"] is True
    assert provenance["coordinator_port"] == 18103
    assert provenance["lane"]["inference_host"] == "Tower3"


def test_remote_lane_provenance_fails_closed_when_manifest_has_no_match():
    provenance = MODULE._manifest_lane_provenance(
        {"topology": {"lanes": []}},
        "http://127.0.0.1:18103/v1/chat/completions",
    )
    assert provenance == {"coordinator_port": 18103, "matched": False, "lane": None}

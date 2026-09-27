#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).with_name("bench_report.py")
SPEC = importlib.util.spec_from_file_location("bench_report", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_config_selects_arbitrary_qwen38_arms_and_checkout_logs(tmp_path):
    config = tmp_path / "campaign.json"
    config.write_text(json.dumps({
        "model": "Qwen3.8-27B-UD-Q4_K_XL",
        "arms": [
            {"label": "qwen38-nothink", "thinking": "off", "pretty": "Qwen no-think"},
            {"label": "qwen38-think-xhigh", "thinking": "on", "pretty": "Qwen think xhigh"},
        ],
    }))
    configured = MODULE.configure_campaign(config=config)
    assert configured["model"] == "Qwen3.8-27B-UD-Q4_K_XL"
    assert MODULE.NOTHINK_LABEL == "qwen38-nothink"
    assert MODULE.THINK_LABEL == "qwen38-think-xhigh"
    assert configured["arms"][1][1] == "Qwen think xhigh"
    assert MODULE.DEFAULT_LOGS == SCRIPT.parent.parent / "logs"


def test_explicit_arm_specs_are_supported_without_config():
    configured = MODULE.configure_campaign(
        arm_specs=["custom-nothink=No think", "custom-think=Think"],
        model_name="Custom model",
    )
    assert configured == {
        "model": "Custom model",
        "arms": [("custom-nothink", "No think"), ("custom-think", "Think")],
    }

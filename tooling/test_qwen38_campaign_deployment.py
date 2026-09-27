#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path


SCRIPT = (Path(__file__).with_name("deployments") /
          "qwen3.8-27b-q4-fleet" / "validate_campaign_deployment.py")
SPEC = importlib.util.spec_from_file_location("qwen38_campaign_validator", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_committed_qwen38_campaign_bundle_is_internally_consistent():
    assert MODULE.validate() == []


def test_validator_detects_sampler_drift(tmp_path):
    manifest = json.loads(MODULE.DEFAULT_MANIFEST.read_text())
    manifest["sampling"]["thinking"]["temperature"] = 0.1
    changed = tmp_path / "manifest.json"
    changed.write_text(json.dumps(manifest))
    errors = MODULE.validate(changed, MODULE.REPO)
    assert any("on arm benchmark_temperature" in error for error in errors)


def test_validator_detects_existing_tunnel_receipt_drift(tmp_path):
    manifest = json.loads(MODULE.DEFAULT_MANIFEST.read_text())
    manifest["topology"]["lanes"][0]["tunnel_unit_sha256"] = "0" * 64
    changed = tmp_path / "manifest.json"
    changed.write_text(json.dumps(manifest))
    errors = MODULE.validate(changed, MODULE.REPO)
    assert any("existing tunnel unit hashes" in error for error in errors)


def test_launcher_reuses_tunnels_and_keeps_check_mode_non_mutating():
    launcher = SCRIPT.with_name("ensure-qwen38-lanes.sh").read_text()
    assert "REMOTE_PORT=11434" in launcher
    assert "dream-fleet-tunnel-tower1.service" in launcher
    assert "dream-fleet-tunnel-tower3.service" in launcher
    assert "systemctl --user start" not in launcher
    assert "systemctl --user restart" not in launcher
    assert "systemctl --user link" not in launcher
    assert "docker run" in launcher
    assert "production container ods-llama-server is still running" in launcher

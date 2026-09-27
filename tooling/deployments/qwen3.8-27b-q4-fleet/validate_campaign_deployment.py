#!/usr/bin/env python3
"""Offline validator for the pinned Tower1/Tower3 Qwen3.8 campaign bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_MANIFEST = HERE / "benchmark-serving-manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(manifest_path: Path = DEFAULT_MANIFEST, repo: Path = REPO) -> list[str]:
    errors: list[str] = []
    manifest = json.loads(manifest_path.read_text())

    def expect(actual, expected, label):
        if actual != expected:
            errors.append(f"{label}: expected {expected!r}, got {actual!r}")

    expect(manifest.get("schema_version"), 2, "manifest schema")
    expect(manifest.get("status"), "prepared_not_started", "manifest status")
    expect(manifest["model"]["sha256"],
           "bee238bbeb3dc0a34bde4d0dedbaee1f98c009e8bb4226f03070054c12fb1372",
           "model sha256")
    expect(manifest["model"]["byte_size"], 17923394624, "model byte size")
    expect(manifest["runtime"]["image_id"],
           "sha256:0c8dc7c0954fe5e1d75118a4f880f17252f62d1d01e24716b172afe9fafd85a1",
           "runtime image")
    expect(manifest["runtime"]["llama_server_sha256"],
           "fc6a6a15230a2dd6c56aae913e6d0d1b4913015e0966d800c08da8dce57b376e",
           "llama-server sha256")
    expect(manifest["topology"]["lane_ports"], [18101, 18103], "lane ports")
    expect(manifest["topology"]["remote_loopback_port"], 11434,
           "remote loopback port")
    expect(manifest["topology"]["slots_per_replica"], 1, "slots per replica")
    expect(manifest["serving"]["context_tokens"], 262144, "serving context")
    expect(manifest["serving"]["kv_cache_k"], "q8_0", "K cache")
    expect(manifest["serving"]["kv_cache_v"], "q8_0", "V cache")
    expect(manifest["serving"]["reasoning_format"], "none", "reasoning format")
    expect(manifest["serving"]["mtp_speculative_decoding"],
           "disabled_pending_quality_parity_evidence", "MTP state")

    lanes = manifest["topology"]["lanes"]
    expect([lane["coordinator_port"] for lane in lanes], [18101, 18103],
           "lane coordinator ports")
    expect([lane["inference_host"] for lane in lanes], ["tower1", "tower3"],
           "lane hosts")
    expect([lane["tunnel_unit"] for lane in lanes],
           ["dream-fleet-tunnel-tower1.service",
            "dream-fleet-tunnel-tower3.service"],
           "existing tunnel units")
    expect([lane["tunnel_unit_sha256"] for lane in lanes],
           ["f096ffcfbe17c5875f9fc8df01612f559d3439646c4d5ef47d810fd3918b163c",
            "13796b4386dca90d2c1f2806e8ed0314321758ab8e891e41d4203450e5728a2f"],
           "existing tunnel unit hashes")
    if len({lane["gpu_uuid"] for lane in lanes}) != 2:
        errors.append("lane GPU UUIDs are not unique")
    for lane in lanes:
        expect(lane["gpu_power_limit_w"], 500,
               f"lane {lane['lane_index']} power limit")
        expect(lane["remote_port"], 11434,
               f"lane {lane['lane_index']} remote port")

    expect(manifest["safety"]["launcher_never_mutates_existing_tunnels"], True,
           "tunnel mutation policy")

    for artifact in manifest["prepared_artifacts"]:
        path = repo / artifact["path"]
        if not path.is_file():
            errors.append(f"prepared artifact missing: {path}")
        elif sha256(path) != artifact["sha256"]:
            errors.append(f"prepared artifact hash mismatch: {artifact['path']}")

    campaign_files = {
        "config_sha256": "tooling/qwen3.8-27b-q4-t1-t3-mmbt.json",
        "autopilot_sha256": "tooling/bench_autopilot.py",
        "harness_sha256": "tooling/harness.py",
        "run_microbench_sha256": "tooling/scripts/run_microbench.sh",
        "grade_microbench_sha256": "tooling/scripts/grade_microbench.sh",
    }
    for key, relative in campaign_files.items():
        path = repo / relative
        if not path.is_file():
            errors.append(f"campaign artifact missing: {relative}")
        elif sha256(path) != manifest["campaign"][key]:
            errors.append(f"campaign artifact hash mismatch: {relative}")

    config_path = repo / manifest["campaign"]["config"]
    config = json.loads(config_path.read_text())
    expect(config["model"], manifest["model"]["served_alias"], "config model alias")
    expect(config["lane_ports"], manifest["topology"]["lane_ports"], "config lane ports")
    expect(config["max_model_len"], manifest["serving"]["context_tokens"],
           "config context")
    expect(config["benchmark_max_output_tokens_cap"], 262144, "output cap")
    expect(config["benchmark_seed"], manifest["sampling"]["seed"], "seed")
    expect(config["benchmark_sandbox_gpus"], "none", "sandbox GPU policy")
    expect(config["services"], [lane["tunnel_unit"] for lane in lanes],
           "config tunnel services")

    arms = {arm["thinking"]: arm for arm in config["arms"]}
    for mode, sampling_key in (("on", "thinking"), ("off", "non_thinking")):
        arm = arms[mode]
        point = manifest["sampling"][sampling_key]
        expected_fields = {
            "preserve_thinking": point["preserve_thinking"],
            "benchmark_temperature": point["temperature"],
            "benchmark_top_p": point["top_p"],
            "benchmark_top_k": point["top_k"],
            "benchmark_min_p": point["min_p"],
            "benchmark_presence_penalty": point["presence_penalty"],
            "benchmark_repeat_penalty": point["repeat_penalty"],
        }
        for key, value in expected_fields.items():
            expect(arm.get(key), value, f"{mode} arm {key}")
    expect(arms["on"].get("reasoning_effort"), "xhigh", "thinking effort")
    expect(arms["on"].get("reasoning_effort_location"), "top_level",
           "thinking effort location")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--repo", type=Path, default=REPO)
    args = parser.parse_args()
    errors = validate(args.manifest.resolve(), args.repo.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("QWEN38_CAMPAIGN_DEPLOYMENT_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

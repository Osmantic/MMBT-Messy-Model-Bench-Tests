#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).with_name("scripts") / "run_microbench.sh"


def _write_executable(path, body):
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body)
    path.chmod(0o755)


def test_qwen38_arm_controls_reach_harness_and_sandbox_gpu_is_omitted(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture = tmp_path / "harness-argv.txt"
    _write_executable(bin_dir / "curl", "exit 0\n")
    _write_executable(
        bin_dir / "python3",
        'printf "%s\\n" "$@" > "$BENCH_TEST_CAPTURE"\n',
    )
    env = dict(os.environ)
    env.update({
        "PATH": f"{bin_dir}:{env['PATH']}",
        "BENCH_TEST_CAPTURE": str(capture),
        "BENCH_LANE_INDEX": "0",
        "BENCH_LANE_COUNT": "12",
        "BENCH_TEMP": "1.0",
        "BENCH_TOP_P": "0.95",
        "BENCH_TOP_K": "20",
        "BENCH_MIN_P": "0.0",
        "BENCH_PRESENCE_PENALTY": "0.0",
        "BENCH_REPEAT_PENALTY": "1.0",
        "BENCH_SEED": "42",
        "BENCH_PRESERVE_THINKING": "true",
        "BENCH_REASONING_EFFORT_LOCATION": "top_level",
        "BENCH_SANDBOX_GPUS": "none",
    })
    result = subprocess.run(
        ["bash", str(SCRIPT), "Qwen3.8-27B-UD-Q4_K_XL", "18101",
         "qwen38-think-xhigh", "1", "xhigh", "on", "262144"],
        cwd=SCRIPT.parent.parent.parent,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    argv = capture.read_text().splitlines()
    expected_pairs = {
        "--temperature": "1.0",
        "--top-p": "0.95",
        "--top-k": "20",
        "--min-p": "0.0",
        "--presence-penalty": "0.0",
        "--repeat-penalty": "1.0",
        "--seed": "42",
        "--reasoning-effort": "xhigh",
        "--reasoning-effort-location": "top_level",
        "--thinking": "on",
        "--preserve-thinking": "on",
        "--max-model-len": "262144",
    }
    for flag, value in expected_pairs.items():
        index = argv.index(flag)
        assert argv[index + 1] == value
    assert "--gpus" not in argv

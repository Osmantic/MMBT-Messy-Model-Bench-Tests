#!/usr/bin/env python3
"""Verification harness: non-mutation, idempotence, write-guard, invariant."""
import csv, hashlib, json, subprocess, sys, shutil
from pathlib import Path

SCRIPT = "/home/michael/pr-staging/tooling/apply_grade_corrections.py"
OUT = Path("/home/michael/pr-staging/overlay")
ROOT = Path("/home/michael")

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

rows = list(csv.DictReader(open("/home/michael/mmbt-frozen-dataset-v2.csv")))

# ---- snapshot every protected file BEFORE ----
protected = []
for r in rows:
    g = ROOT / r["repo"] / "logs" / r["cell"] / "grade.json"
    if g.is_file():
        protected.append(g)
for repo in {r["repo"] for r in rows}:
    for sub in ("tooling/tasks", "tooling/graders/ground_truth"):
        d = ROOT / repo / sub
        if d.is_dir():
            protected.extend(sorted(p for p in d.rglob("*") if p.is_file()))
before = {str(p): (sha(p), p.stat().st_mtime_ns) for p in protected}
print(f"protected files snapshotted: {len(before)}")

# ---- run 1 ----
if OUT.exists():
    shutil.rmtree(OUT)
r1 = subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True)
print("run1 rc:", r1.returncode)
print("run1 out:", r1.stdout.strip()[:300])
if r1.stderr.strip():
    print("run1 err:", r1.stderr.strip()[:600])
files1 = {str(p.relative_to(OUT)): sha(p) for p in OUT.rglob("*.json") if p.name != "manifest.json"}
m1 = json.loads((OUT / "manifest.json").read_text())

# ---- run 2 (idempotence) ----
r2 = subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True)
print("run2 rc:", r2.returncode)
files2 = {str(p.relative_to(OUT)): sha(p) for p in OUT.rglob("*.json") if p.name != "manifest.json"}
m2 = json.loads((OUT / "manifest.json").read_text())

print()
print("=== IDEMPOTENCE ===")
print("  per-cell files run1:", len(files1), " run2:", len(files2))
print("  identical file set :", set(files1) == set(files2))
diffs = [k for k in files1 if files1.get(k) != files2.get(k)]
print("  byte-differing files:", len(diffs), diffs[:5])
print("  overlay_digest run1 :", m1["overlay_digest"])
print("  overlay_digest run2 :", m2["overlay_digest"])
print("  digest stable       :", m1["overlay_digest"] == m2["overlay_digest"])
print("  generated_at differs:", m1["generated_at"] != m2["generated_at"], "(expected True)")

# ---- non-mutation ----
print()
print("=== NON-MUTATION OF RUN EVIDENCE ===")
changed = [p for p, v in before.items() if (sha(Path(p)), Path(p).stat().st_mtime_ns) != v]
print(f"  protected files checked : {len(before)}")
print(f"  protected files changed : {len(changed)}")
for c in changed[:10]:
    print("    CHANGED:", c)
stray = [str(p) for p in ROOT.glob("mmbt-*/logs/*/grade.corrected.json")]
print(f"  stray grade.corrected.json inside checkouts : {len(stray)}")

# ---- write guard ----
print()
print("=== WRITE GUARD ===")
sys.path.insert(0, "/home/michael/pr-staging/tooling")
import apply_grade_corrections as A
targets = [
    ROOT / "mmbt-q36-card/logs/p3_pm_qwen36-nothink-card_v2/grade.json",
    ROOT / "mmbt-q36-card/tooling/tasks/task_triage.md",
    ROOT / "mmbt-q36-card/tooling/graders/ground_truth/phase2_triage.json",
    ROOT / "mmbt-q36-card/logs/p3_pm_qwen36-nothink-card_v2/receipt.json",
]
for t in targets:
    try:
        A.guarded_write(t, "SHOULD NEVER BE WRITTEN")
        print("  !! NOT REFUSED:", t)
    except A.ProtectedPathError as e:
        print("  refused OK:", t.relative_to(ROOT), "->", str(e).split(":")[-1].strip()[:60])
# and confirm a legitimate target is allowed
ok = OUT / "_guard_probe.json"
A.guarded_write(ok, "{}\n")
print("  allowed OK:", ok.name, ok.is_file())
ok.unlink()

print()
print("=== MANIFEST INVARIANT ===")
print("  invariant_checked   :", m1["invariant_checked"])
print("  invariant_violations:", len(m1["invariant_violations"]))
print("  post_freeze_divergence:", len(m1["post_freeze_divergence"]))
print("  frozen dataset sha256:", m1["frozen_dataset_sha256"])

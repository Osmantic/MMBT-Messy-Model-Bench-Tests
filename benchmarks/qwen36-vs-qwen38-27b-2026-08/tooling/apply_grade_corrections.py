#!/usr/bin/env python3
"""Non-destructive grader-correction overlay for the Qwen3.6 vs Qwen3.8 MMBT PR.

WHAT THIS IS
============
Three grader defects were identified in the MMBT harness.  Repo convention is that
`grade.json`, the task briefs under `tooling/tasks/`, and the ground-truth files under
`tooling/graders/ground_truth/` are IMMUTABLE run evidence: they are never edited, so
that grades stay longitudinally comparable with every earlier campaign.  Corrections are
therefore published as a separate overlay.  This script produces that overlay.

For every cell it corrects, it emits a `grade.corrected.json` carrying the original
verdict, the correction outcome, which defect(s) fired, and the measured evidence that
justifies the change.  It never mutates a single byte of run evidence.

The outcome takes two deliberately distinct shapes.  D2/D3 corrections ARE verdict
corrections and carry `corrected_verdict`.  D1 corrections are GATE INVALIDATIONS and
carry `gate_invalidated: true` plus `verdict_without_length_gate` -- and, unless a D2/D3
verdict correction also fired on the same cell, NO `corrected_verdict` at all, so a
downstream aggregator that reads the field (not the prose) cannot mistake a length-gate
invalidation for a verified PASS.

THE THREE DEFECTS
=================
D1 -- WORD-GATE TOKENIZER MISMATCH
    The four phase-3 length-gated graders measure length with
    `len(re.findall(r"\\b\\w+\\b", text))`.  The models budget with shell `wc -w`.  The two
    counters disagree because `wc -w` counts whitespace-delimited runs (so markdown
    punctuation such as `|`, `---`, `**` and `#` become "words") while the regex counts
    alphanumeric runs (so a hyphenated token like `mid-July` counts twice).
    NEITHER COUNTER IS GROUND TRUTH.  The honest framing is that two reasonable counters
    disagree by more than the margin at a hard threshold, and the model was optimising
    against the one it could actually observe.  This overlay reports both numbers side by
    side and, where a FAIL is attributable to the length gate ALONE and every deliverable
    is within its ceiling under `wc -w`, records `gate_invalidated: true` together with
    `verdict_without_length_gate` (computed from the non-length gates).  Per the
    grader-defects doc these cells are to be read as "not a valid FAIL", NOT as "a
    verified PASS", which is why a D1-only cell carries no `corrected_verdict`.

D2 -- p3_pm KEYWORD LITERALISM
    `phase3_project_mgmt_grade.py` RISK_KEYWORDS R3 requires one of the literal strings
    "legal unresponsive" / "legal silent" / "legal hasn't" / "blocking on legal".
    Qwen3.6 characteristically writes the uncontracted "legal has not responded", which is
    semantically identical and literally unmatched.
    The repo ALREADY CONTAINS the fix, unit-tested, in
    `tooling/correct_gemma4_project_mgmt_grades.py` -- but its cell enumeration was
    hardcoded to `p3_pm_gemma4-31b-q4_v{n}`.  We REUSE that module rather than
    reimplementing it (see `load_upstream_pm_corrector` and `correct_project_mgmt`), and
    generalise it by driving cell selection from the frozen dataset instead.
    MECHANISM, PRECISELY: upstream R3 is an ADJACENCY REGEX -- `legal` within 200
    characters of a completion term (has not / not yet responded / sign-off / approval /
    unresponsive / silent / delay / contract) -- which matches strictly more than
    contractions.  So the overlay records, for every corrected cell, the exact span of
    report text the regex matched (`matched_span`), making the applied mechanism
    self-documenting rather than relying on the "contraction literalism" shorthand.

D3 -- p2_triage BRIEF / GROUND-TRUTH CONTRADICTION
    `tooling/tasks/task_triage.md` defines an urgency value for noise/spam.  The ground
    truth `tooling/graders/ground_truth/phase2_triage.json` labels the spam tickets with a
    different value, and the grader does exact string match.  Every graded triage cell of
    both models followed the brief and was penalised for it.  The allowed vocabulary and
    the noise category are PARSED OUT OF THE BRIEF (see `parse_triage_brief`) rather than
    hardcoded, so the correction is traceable to the document that authorised it.

ALL THREE CORRECTIONS ARE STRICTLY LENIENCY.  The script verifies empirically -- over
every graded cell, not just the corrected ones -- that no cell flips PASS -> FAIL.

SAFETY
======
`guarded_write` refuses, with a hard error, to write to `grade.json`, to anything under
`tooling/tasks/`, or to anything under a `ground_truth/` directory.  The default output
root is a MIRROR tree under the PR staging directory:

    <output-root>/<repo>/logs/<cell>/grade.corrected.json

which is byte-for-byte the sibling layout the overlay takes inside the repo, so it can be
dropped in at merge time without this script ever touching a checkout.  `--in-place`
writes true siblings into the checkouts instead; it is off by default and still cannot
touch protected paths.

IDEMPOTENCE
===========
Every per-cell payload is deterministic: sorted keys, no wall-clock, no absolute paths
that vary by run.  Re-running produces byte-identical per-cell files.  The manifest
carries `overlay_digest`, a sha256 over all per-cell payloads, which is the value to
compare across runs; `generated_at` in the manifest is the only volatile field and is
excluded from the digest.

USAGE
=====
    apply_grade_corrections.py --dry-run          # print summary table, write nothing
    apply_grade_corrections.py                    # write the overlay mirror
    apply_grade_corrections.py --json-summary out.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tarfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "mmbt-grade-correction-overlay/2"

DEFAULT_CHECKOUT_ROOT = Path("/home/michael")
DEFAULT_DATASET = Path("/home/michael/mmbt-frozen-dataset-v2.csv")
DEFAULT_OUTPUT_ROOT = Path("/home/michael/pr-staging/overlay")

# Freeze #2 stamp (see /home/michael/FREEZE2_STAMP.txt). Freeze #1
# (mmbt-frozen-dataset.csv, 746 cells, 2026-08-16T11:49:14Z) is superseded.
FREEZE_STAMP = "2026-08-16T14:23:09Z"

# The frozen dataset is the single source of truth for cell identity, model and sampler.
# Identity is NEVER recomputed from directory names.
FROZEN_DATASET_NOTE = (
    "cell identity, model and sampler are taken verbatim from the frozen dataset; "
    "never recomputed from directory names"
)


# ---------------------------------------------------------------------------
# Write guard
# ---------------------------------------------------------------------------

class ProtectedPathError(RuntimeError):
    """Raised when something tries to write to immutable run evidence."""


PROTECTED_BASENAMES = {"grade.json", "receipt.json", "transcript.jsonl", "summary.json"}
PROTECTED_DIR_NAMES = {"ground_truth", "tasks"}


def assert_writable(path: Path) -> None:
    """Hard-refuse any write to immutable run evidence.

    Refuses grade.json (and its sibling run evidence), anything under a `tasks/`
    directory (the task briefs), and anything under a `ground_truth/` directory.
    """
    resolved = Path(path).resolve()
    if resolved.name in PROTECTED_BASENAMES:
        raise ProtectedPathError(
            f"REFUSING to write {resolved}: {resolved.name} is immutable run evidence. "
            "Corrections are published as a separate overlay, never by editing grades."
        )
    for part in resolved.parts:
        if part in PROTECTED_DIR_NAMES:
            raise ProtectedPathError(
                f"REFUSING to write {resolved}: it lives under a protected '{part}/' "
                "directory (task briefs and ground truth are immutable)."
            )


def guarded_write(path: Path, text: str) -> None:
    assert_writable(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def read_tar_member(archive: Path, relname: str) -> bytes | None:
    """Return the exact bytes of a top-level workspace deliverable, or None.

    Requires exactly one match so an ambiguous archive is never silently mis-measured.
    """
    with tarfile.open(archive, "r:gz") as bundle:
        matches = [
            m for m in bundle.getmembers()
            if m.isfile() and m.name.removeprefix("./") == relname
        ]
        if len(matches) != 1:
            return None
        handle = bundle.extractfile(matches[0])
        if handle is None:
            return None
        return handle.read()


# ---------------------------------------------------------------------------
# D1: word counting
# ---------------------------------------------------------------------------

# The grader's counter, verbatim from the four phase-3 length-gated graders:
#   phase3_business_memo_grade.py:73, phase3_doc_synthesis_grade.py:48,
#   phase3_project_mgmt_grade.py:64, phase3_writing_editing_grade.py:18
GRADER_WORD_RE = re.compile(r"\b\w+\b")

# GNU wc -w counts maximal runs of non-whitespace characters.  Whitespace is
# space, tab, newline, vertical tab, form feed, carriage return.
_WC_WHITESPACE = b" \t\n\v\f\r"

# LOCALE MATTERS, AND IT IS NOT A DETAIL.
# GNU wc's word counter skips characters that are not printable in the active locale.
# Under LC_ALL=C every byte >= 0x80 is non-printable, so a standalone em dash (U+2014,
# three high bytes between two spaces) forms NO word at all -- these deliverables are
# full of em dashes, and the C locale undercounts one of them by 17 words out of 700.
# The harness container is the authority on which count the model actually saw:
#     docker image inspect bench-sandbox:latest --format "{{json .Config.Env}}"
#       -> [..., "LANG=C.UTF-8", ...]
# and `wc -w` run inside that image reproduces the C.UTF-8 number, not the C number.
# So we pin C.UTF-8. Pinning C here would silently inflate the correction count.
_HARNESS_LOCALE = "C.UTF-8"
_HARNESS_LOCALE_PROVENANCE = (
    "bench-sandbox:latest Config.Env LANG=C.UTF-8; verified by running wc -w inside "
    "that image against an extracted deliverable"
)


def grader_word_count(text: str) -> int:
    return len(GRADER_WORD_RE.findall(text))


def wc_w_pure_python(data: bytes) -> int:
    """Byte-level reimplementation of the GNU `wc -w` word-counting loop."""
    count = 0
    in_word = False
    for byte in data:
        if byte in _WC_WHITESPACE:
            in_word = False
        elif not in_word:
            in_word = True
            count += 1
    return count


def wc_w_subprocess(data: bytes) -> int | None:
    """Run the real `wc -w` binary on the exact deliverable bytes, in the harness locale."""
    try:
        proc = subprocess.run(
            ["wc", "-w"], input=data, capture_output=True, check=True,
            env={"LC_ALL": _HARNESS_LOCALE, "LANG": _HARNESS_LOCALE,
                 "PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    try:
        return int(proc.stdout.split()[0])
    except (IndexError, ValueError):
        return None


def measure_deliverable(data: bytes) -> dict:
    """Measure one deliverable with both counters. No guessed percentages anywhere."""
    text = data.decode("utf-8", errors="replace")
    shell = wc_w_subprocess(data)
    pure = wc_w_pure_python(data)
    return {
        "bytes": len(data),
        "sha256": sha256_bytes(data),
        "grader_regex_word_count": grader_word_count(text),
        "wc_w_count": shell if shell is not None else pure,
        "wc_w_source": (
            f"shell wc -w under LC_ALL={_HARNESS_LOCALE}" if shell is not None
            else "pure-python wc -w equivalent"
        ),
        "wc_w_locale": _HARNESS_LOCALE,
        "wc_w_locale_provenance": _HARNESS_LOCALE_PROVENANCE,
        "wc_w_shell": shell,
        "wc_w_pure_python": pure,
        "wc_w_counters_agree": (shell is None or shell == pure),
    }


def transcript_wc_w_calls(cell_dir: Path) -> int | None:
    """Count literal `wc -w` invocations in the transcript.

    This is the evidence that `wc -w` is the counter the model was actually budgeting
    against -- it is not used to decide any correction, only to document why the
    disagreement matters.
    """
    path = cell_dir / "transcript.jsonl"
    if not path.is_file():
        return None
    total = 0
    with path.open("rb") as handle:
        carry = b""
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            buf = carry + chunk
            total += buf.count(b"wc -w")
            carry = buf[-8:]
    return total


# ---------------------------------------------------------------------------
# D1: per-grader length-gate models
#
# Each entry describes, for one length-gated grader: the deliverables it word-counts,
# and whether every NON-length gate passed.  A FAIL is "length-attributable" only when
# every other gate passed and the sole failing condition was the word ceiling.
# ---------------------------------------------------------------------------

def _pm_recall(value: str | None) -> int:
    # project_mgmt stores recalls as "n/6" strings.
    if not isinstance(value, str) or "/" not in value:
        return -1
    try:
        return int(value.split("/")[0])
    except ValueError:
        return -1


def length_profile_business_memo(grade: dict) -> dict | None:
    scores = grade.get("scores") or {}
    thresholds = grade.get("thresholds") or {}
    ceiling = thresholds.get("max_word_count")
    if ceiling is None or "memo_word_count" not in scores:
        return None
    # Gate, verbatim: bias_recall >= min_bias_recall AND stance_pushback AND wc <= ceiling
    others_pass = (
        (scores.get("bias_recall") or 0) >= thresholds.get("min_bias_recall", 0.5)
        and bool(scores.get("stance_pushback"))
    )
    return {
        "deliverables": [{"relname": "memo.md", "ceiling": ceiling,
                          "stored_grader_count": scores.get("memo_word_count")}],
        "non_length_gates_pass": others_pass,
        "gate_source": "phase3_business_memo_grade.py:115",
    }


def length_profile_doc_synthesis(grade: dict) -> dict | None:
    scores = grade.get("scores") or {}
    thresholds = grade.get("thresholds") or {}
    ceiling = thresholds.get("max_word_count")
    if ceiling is None or "word_count" not in scores:
        return None
    others_pass = (
        (scores.get("facts_captured") or 0) >= thresholds.get("min_facts_captured", 6)
    )
    return {
        "deliverables": [{"relname": "brief.md", "ceiling": ceiling,
                          "stored_grader_count": scores.get("word_count")}],
        "non_length_gates_pass": others_pass,
        "gate_source": "phase3_doc_synthesis_grade.py:70",
    }


def length_profile_project_mgmt(grade: dict) -> dict | None:
    scores = grade.get("scores") or {}
    thresholds = grade.get("thresholds") or {}
    ceiling = thresholds.get("max_word_count")
    if ceiling is None or "word_count" not in scores:
        return None
    others_pass = (
        _pm_recall(scores.get("workstream_recall")) >= thresholds.get("min_workstreams", 4)
        and _pm_recall(scores.get("risk_recall")) >= thresholds.get("min_risks", 3)
        and _pm_recall(scores.get("decision_recall")) >= thresholds.get("min_decisions", 3)
        and _pm_recall(scores.get("milestone_recall")) >= thresholds.get("min_milestones", 3)
        and len(scores.get("sections_present") or []) >= 3
    )
    return {
        "deliverables": [{"relname": "status_report.md", "ceiling": ceiling,
                          "stored_grader_count": scores.get("word_count")}],
        "non_length_gates_pass": others_pass,
        "gate_source": "phase3_project_mgmt_grade.py:95-102",
    }


def length_profile_writing_editing(grade: dict) -> dict | None:
    per_audience = grade.get("per_audience") or {}
    if not per_audience:
        return None
    deliverables = []
    others_pass = True
    for audience, result in sorted(per_audience.items()):
        if result.get("verdict") == "MISSING" or "word_count" not in result:
            return None  # a missing deliverable is not a length problem
        if not (result.get("required_content_pass") and result.get("prohibited_content_pass")):
            others_pass = False
        deliverables.append({
            "relname": result.get("filename"),
            "audience": audience,
            "ceiling": result.get("max_words"),
            "stored_grader_count": result.get("word_count"),
        })
    return {
        "deliverables": deliverables,
        "non_length_gates_pass": others_pass,
        "gate_source": "phase3_writing_editing_grade.py:110 (all audiences must PASS)",
    }


LENGTH_GATED_GRADERS = {
    "business_memo": length_profile_business_memo,
    "doc_synthesis": length_profile_doc_synthesis,
    "project_mgmt": length_profile_project_mgmt,
    "writing_editing": length_profile_writing_editing,
}


def correct_word_gate(cell_dir: Path, grade: dict) -> dict | None:
    """Apply D1. Returns None when the cell is not a length-gate candidate."""
    task = grade.get("task")
    profile_fn = LENGTH_GATED_GRADERS.get(task)
    if profile_fn is None:
        return None
    profile = profile_fn(grade)
    if profile is None:
        return None

    archive = cell_dir / "workspace_final.tar.gz"
    if not archive.is_file():
        return None

    measurements = []
    all_within_wc_w = True
    any_over_grader = False
    extraction_verified = True
    for spec in profile["deliverables"]:
        relname = spec.get("relname")
        ceiling = spec.get("ceiling")
        if not relname or ceiling is None:
            extraction_verified = False
            break
        data = read_tar_member(archive, relname)
        if data is None:
            extraction_verified = False
            break
        m = measure_deliverable(data)
        m["relname"] = relname
        if "audience" in spec:
            m["audience"] = spec["audience"]
        m["ceiling"] = ceiling
        m["stored_grader_count"] = spec.get("stored_grader_count")
        # INTEGRITY CHECK: re-running the grader's own counter on the bytes we extracted
        # must reproduce the number the grader recorded.  If it does not, we are not
        # looking at the artifact the grader looked at, and we refuse to correct.
        m["grader_recount_matches_stored"] = (
            m["grader_regex_word_count"] == spec.get("stored_grader_count")
        )
        if not m["grader_recount_matches_stored"]:
            extraction_verified = False
        m["over_ceiling_by_grader_regex"] = m["grader_regex_word_count"] > ceiling
        m["within_ceiling_by_wc_w"] = m["wc_w_count"] <= ceiling
        m["counter_delta"] = m["grader_regex_word_count"] - m["wc_w_count"]
        if m["over_ceiling_by_grader_regex"]:
            any_over_grader = True
        if not m["within_ceiling_by_wc_w"]:
            all_within_wc_w = False
        measurements.append(m)

    if not measurements:
        return None

    length_attributable_fail = bool(
        grade.get("verdict") == "FAIL"
        and profile["non_length_gates_pass"]
        and any_over_grader
    )
    applies = bool(
        length_attributable_fail and extraction_verified and all_within_wc_w
    )
    return {
        "defect": "D1",
        "applies": applies,
        "title": "word-gate tokenizer mismatch",
        "gate_source": profile["gate_source"],
        "non_length_gates_pass": profile["non_length_gates_pass"],
        "length_attributable_fail": length_attributable_fail,
        "extraction_verified": extraction_verified,
        "any_deliverable_over_ceiling_by_grader_regex": any_over_grader,
        "all_deliverables_within_ceiling_by_wc_w": all_within_wc_w,
        "measurements": measurements,
        "model_wc_w_calls_in_transcript": transcript_wc_w_calls(cell_dir),
        "framing": (
            "neither counter is ground truth: wc -w counts markdown punctuation as words, "
            "the grader regex splits hyphenated tokens. Two reasonable counters disagree "
            "by more than the margin at a hard threshold."
        ),
    }


# ---------------------------------------------------------------------------
# D2: reuse of the repo's existing, unit-tested project-management corrector
# ---------------------------------------------------------------------------

_UPSTREAM_CACHE: dict[str, object] = {}


def load_upstream_pm_corrector(repo_root: Path):
    """Import the repo's own `tooling/correct_gemma4_project_mgmt_grades.py`.

    We deliberately do NOT reimplement its rules.  We import the module and call its
    `apply_correction` so the overlay uses the same regexes and the same verdict
    recomputation that the repo already unit-tests in
    `tooling/test_correct_gemma4_project_mgmt_grades.py`.

    The ONLY thing we change is cell selection: upstream `build()` hardcodes the names
    `p3_pm_gemma4-31b-q4_v{n}`, which is why it never ran against the Qwen cells.  We
    bypass `build()` entirely and drive selection from the frozen dataset instead.
    """
    path = repo_root / "tooling" / "correct_gemma4_project_mgmt_grades.py"
    if not path.is_file():
        raise FileNotFoundError(f"upstream corrector missing: {path}")
    digest = sha256_file(path)
    if digest in _UPSTREAM_CACHE:
        return _UPSTREAM_CACHE[digest], digest, path
    spec = importlib.util.spec_from_file_location(f"upstream_pm_{digest[:12]}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _UPSTREAM_CACHE[digest] = module
    return module, digest, path


@contextmanager
def upstream_rules_scoped(module, rule_ids: set[str] | None):
    """Narrow upstream's RULES table to the rules this PR actually verified.

    Upstream ships four semantic-equivalence rules (R2, R3, D3_mobile, D4_option_b).
    This PR verified only R3 firsthand -- the "legal has not responded" vs "legal hasn't"
    natural experiment.  Applying rules we did not verify would be a broader correction
    than the PR claims, so by default we scope upstream to R3.  `--pm-rules all` restores
    the full upstream table for reviewers who want to see the wider effect.
    """
    if rule_ids is None:
        yield sorted(module.RULES)
        return
    original = module.RULES
    module.RULES = {k: v for k, v in original.items() if k in rule_ids}
    try:
        yield sorted(module.RULES)
    finally:
        module.RULES = original


def correct_project_mgmt(cell_dir: Path, repo_root: Path, grade: dict,
                         rule_ids: set[str] | None) -> dict | None:
    """Apply D2 by delegating to the repo's own corrector."""
    if grade.get("task") != "project_mgmt":
        return None
    archive = cell_dir / "workspace_final.tar.gz"
    if not archive.is_file():
        return None

    module, module_sha256, module_path = load_upstream_pm_corrector(repo_root)
    try:
        report_text, report_sha256 = module.read_archived_report(archive)
    except (OSError, tarfile.TarError, UnicodeDecodeError, ValueError):
        return None

    with upstream_rules_scoped(module, rule_ids) as active_rules:
        corrected_grade, changes = module.apply_correction(grade, report_text)

    # Evidence: for each rule that fired, show the phrase the model actually wrote next to
    # the literal keyword list it failed to match, and record the EXACT span the upstream
    # adjacency regex matched -- the rule matches more than contractions, so the matched
    # span (not the narrative) is the record of the mechanism actually applied.
    literal_misses = {}
    if grade.get("task") == "project_mgmt":
        for change in changes:
            item = change["item"]
            category = change["category"]
            span = _pattern_match_span(report_text, change["pattern"])
            change["matched_span"] = span["matched_span"] if span else None
            literal_misses[item] = {
                "literal_keywords_required_by_grader":
                    _grader_keyword_list(repo_root, category, item),
                "matched_span_of_upstream_pattern": span,
                "matched_phrase_in_report": _first_match_excerpt(
                    report_text, change["pattern"]
                ),
                "semantic_rule": change["reason"],
                "upstream_pattern": change["pattern"],
            }

    return {
        "defect": "D2",
        "applies": bool(changes),
        "title": "p3_pm keyword literalism",
        "mechanism_note": (
            "the rule actually applied is upstream R3, an adjacency regex (the word "
            "legal within 200 characters of a completion term such as has not / "
            "sign-off / approval / unresponsive / silent / delay / contract), which "
            "matches strictly more than contractions; matched_span in each change "
            "records the exact text that satisfied it"
        ),
        "upstream_module": {
            "path_in_repo": "tooling/correct_gemma4_project_mgmt_grades.py",
            "sha256": module_sha256,
            "reused": "read_archived_report + apply_correction (not reimplemented)",
            "generalised_by": (
                "cell selection driven from the frozen dataset instead of upstream "
                "build()'s hardcoded p3_pm_gemma4-31b-q4_v{n} names"
            ),
            "active_rules": active_rules,
        },
        "status_report_source": "workspace_final.tar.gz:./status_report.md",
        "status_report_sha256": report_sha256,
        "changes": changes,
        "evidence": literal_misses,
        "upstream_corrected_verdict": corrected_grade.get("verdict"),
        "corrected_scores": corrected_grade.get("scores"),
        "corrected_details": corrected_grade.get("details"),
    }


_GRADER_KEYWORD_CACHE: dict[tuple[str, str, str], list] = {}


def _grader_keyword_list(repo_root: Path, category: str, item: str) -> list:
    """Read the literal keyword list the grader required, straight from the grader."""
    key = (str(repo_root), category, item)
    if key in _GRADER_KEYWORD_CACHE:
        return _GRADER_KEYWORD_CACHE[key]
    grader = repo_root / "tooling" / "graders" / "phase3_project_mgmt_grade.py"
    table = {"risks": "RISK_KEYWORDS", "decisions": "DECISION_KEYWORDS",
             "workstreams": "WORKSTREAM_KEYWORDS", "milestones": "MILESTONE_KEYWORDS"}.get(category)
    result: list = []
    if grader.is_file() and table:
        src = grader.read_text(encoding="utf-8")
        block = re.search(rf"{table}\s*=\s*\{{(.*?)\n\}}", src, re.S)
        if block:
            row = re.search(rf'"{re.escape(item)}"\s*:\s*\[(.*?)\]', block.group(1), re.S)
            if row:
                result = re.findall(r'"([^"]*)"', row.group(1))
    _GRADER_KEYWORD_CACHE[key] = result
    return result


def _first_match_excerpt(text: str, pattern: str, window: int = 120) -> str | None:
    normalized = re.sub(r"\s+", " ", text.lower())
    hit = re.search(pattern, normalized)
    if not hit:
        return None
    start = max(0, hit.start() - 10)
    return normalized[start:hit.end() + window].strip()[:260]


def _pattern_match_span(text: str, pattern: str) -> dict | None:
    """Return the exact span the upstream rule matched, under upstream's normalisation.

    `apply_correction` searches a lowercased, whitespace-collapsed copy of the report, so
    the span is reported in that same normalisation, with its offsets, and is the
    verbatim text that satisfied the adjacency regex -- no paraphrase, no excerpt window.
    """
    normalized = re.sub(r"\s+", " ", text.lower())
    hit = re.search(pattern, normalized)
    if not hit:
        return None
    return {
        "matched_span": hit.group(0),
        "start_in_normalized_text": hit.start(),
        "end_in_normalized_text": hit.end(),
        "normalization": (
            "lowercased, whitespace collapsed to single spaces "
            "(identical to upstream apply_correction)"
        ),
    }


# ---------------------------------------------------------------------------
# D3: triage brief vs ground truth
# ---------------------------------------------------------------------------

def parse_triage_brief(brief_path: Path) -> dict:
    """Parse the allowed urgency vocabulary and the noise category OUT OF THE BRIEF.

    Nothing here is hardcoded to a particular token: we find the "Urgency (closed
    vocabulary)" bullet list, and within it the value whose definition mentions
    noise/spam.  Likewise for the category vocabulary.  The correction is therefore
    traceable to the exact brief line that authorised the model's answer.
    """
    lines = brief_path.read_text(encoding="utf-8").splitlines()

    def bullets_under(header_re: str) -> list[tuple[int, str, str]]:
        out = []
        inside = False
        for idx, line in enumerate(lines, start=1):
            if re.match(header_re, line.strip(), re.I):
                inside = True
                continue
            if inside and line.startswith("## "):
                break
            if inside:
                m = re.match(r"^-\s+`([^`]+)`\s*[—-]+\s*(.*)$", line.strip())
                if m:
                    out.append((idx, m.group(1), m.group(2)))
        return out

    urgency = bullets_under(r"^##\s*Urgency")
    categories = bullets_under(r"^##\s*Categories")
    if not urgency:
        raise ValueError(f"could not parse urgency vocabulary from {brief_path}")

    noise_re = re.compile(r"noise|spam", re.I)
    noise_urgency = [(n, term, desc) for n, term, desc in urgency if noise_re.search(desc)]
    if len(noise_urgency) != 1:
        raise ValueError(
            f"expected exactly one noise/spam urgency value in {brief_path}, "
            f"found {[t for _, t, _ in noise_urgency]}"
        )
    line_no, term, desc = noise_urgency[0]
    noise_categories = sorted({t for _, t, d in categories if noise_re.search(t) or noise_re.search(d)})
    return {
        "brief_path_in_repo": "tooling/tasks/task_triage.md",
        "urgency_vocabulary": [t for _, t, _ in urgency],
        "category_vocabulary": [t for _, t, _ in categories],
        "noise_urgency_value": term,
        "noise_urgency_brief_line_number": line_no,
        "noise_urgency_brief_line": f"- `{term}` — {desc}",
        "noise_categories": noise_categories,
    }


def load_triage_ground_truth(repo_root: Path) -> dict:
    path = repo_root / "tooling" / "graders" / "ground_truth" / "phase2_triage.json"
    return json.loads(path.read_text(encoding="utf-8"))


def correct_triage(repo_root: Path, grade: dict) -> dict | None:
    """Apply D3: credit brief-compliant noise-urgency answers the ground truth contradicts."""
    if grade.get("task") != "triage":
        return None
    scores = grade.get("scores") or {}
    errors = grade.get("errors") or {}
    if "urgency_accuracy" not in scores:
        return None

    brief = parse_triage_brief(repo_root / "tooling" / "tasks" / "task_triage.md")
    gt = load_triage_ground_truth(repo_root)
    gt_tickets = gt.get("tickets", {})
    n = len(gt_tickets)

    urgency_errors = errors.get("urgency_errors") or []
    category_errors = errors.get("category_errors") or []
    missing = errors.get("missing_tickets") or []

    # Recompute the grader's own arithmetic so the correction is not built on a rounded
    # number, then cross-check against what the grader stored.
    correct_urgency = n - len(urgency_errors) - len(missing)
    correct_category = n - len(category_errors) - len(missing)
    recomputed_urg = round(correct_urgency / n, 3) if n else None
    recomputed_cat = round(correct_category / n, 3) if n else None
    arithmetic_ok = (
        recomputed_urg == scores.get("urgency_accuracy")
        and recomputed_cat == scores.get("category_accuracy")
    )

    noise_value = brief["noise_urgency_value"]
    credited = []
    for err in urgency_errors:
        tid = err.get("id")
        gt_entry = gt_tickets.get(tid) or {}
        if (
            err.get("predicted") == noise_value
            and err.get("actual") != noise_value
            and gt_entry.get("category") in brief["noise_categories"]
        ):
            credited.append({
                "ticket_id": tid,
                "model_answer": err.get("predicted"),
                "ground_truth_label": err.get("actual"),
                "ground_truth_category": gt_entry.get("category"),
                "authorised_by_brief_line": brief["noise_urgency_brief_line_number"],
            })

    if not credited or not arithmetic_ok:
        return {
            "defect": "D3",
            "applies": False,
            "title": "p2_triage brief / ground-truth contradiction",
            "grader_arithmetic_reproduced": arithmetic_ok,
            "credited_tickets": credited,
            "brief": brief,
        }

    corrected_correct = correct_urgency + len(credited)
    corrected_urg = round(corrected_correct / n, 3)
    thresholds = grade.get("thresholds") or {}
    dup_recall = (scores.get("duplicate_recall") or 0)
    corrected_verdict = "PASS" if (
        (recomputed_cat or 0) >= thresholds.get("category_accuracy", 0.80)
        and corrected_urg >= thresholds.get("urgency_accuracy", 0.70)
        and dup_recall >= thresholds.get("duplicate_recall", 0.50)
        and len(missing) == 0
    ) else "FAIL"

    return {
        "defect": "D3",
        "applies": True,
        "title": "p2_triage brief / ground-truth contradiction",
        "brief": brief,
        "ground_truth_path_in_repo": "tooling/graders/ground_truth/phase2_triage.json",
        "contradiction": (
            f"brief line {brief['noise_urgency_brief_line_number']} defines urgency "
            f"'{brief['noise_urgency_value']}' for noise/spam; the ground truth labels "
            f"those same tickets differently, and the grader does exact string match"
        ),
        "grader_arithmetic_reproduced": arithmetic_ok,
        "tickets_total": n,
        "credited_tickets": credited,
        "credited_count": len(credited),
        "urgency_accuracy_original": scores.get("urgency_accuracy"),
        "urgency_accuracy_corrected": corrected_urg,
        "urgency_threshold": thresholds.get("urgency_accuracy", 0.70),
        "category_accuracy": recomputed_cat,
        "duplicate_recall": dup_recall,
        "corrected_verdict": corrected_verdict,
    }


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def compose_verdict(grade: dict, d1: dict | None, d2: dict | None, d3: dict | None) -> dict:
    """Compose the correction outcome from whichever defects fired.

    Two outcome kinds are deliberately distinct in the schema:

    * D2/D3 are VERDICT CORRECTIONS: the grader misread a compliant answer, the corrected
      gate arithmetic yields a real verdict, and the cell carries `corrected_verdict`.
    * D1 is a GATE INVALIDATION: two reasonable word counters disagree at the threshold,
      so the length-gate FAIL is not valid evidence of failure.  That is NOT the same
      claim as a verified PASS, so a D1 cell carries `gate_invalidated: true` plus
      `verdict_without_length_gate` (what the non-length gates yield) and -- unless a
      D2/D3 verdict correction also fired on the same cell -- no `corrected_verdict`.

    Every correction is monotone leniency: a correction can only satisfy a gate that was
    previously unsatisfied.  It can never unsatisfy one.
    """
    outcome = {
        "applied": [],
        "corrected_verdict": None,
        "gate_invalidated": False,
        "verdict_without_length_gate": None,
    }
    d1_fired = bool(d1 and d1.get("applies"))
    if d1_fired:
        outcome["gate_invalidated"] = True

    if d3 and d3.get("applies"):
        outcome["applied"].append("D3")
        outcome["corrected_verdict"] = d3["corrected_verdict"]
        if d1_fired:  # defensive: triage is not length-gated, so this cannot co-fire
            outcome["applied"].append("D1")
            outcome["verdict_without_length_gate"] = d3["corrected_verdict"]
        return outcome

    if grade.get("task") == "project_mgmt":
        d2_fired = bool(d2 and d2.get("applies"))
        if not (d2_fired or d1_fired):
            return outcome
        if d2_fired:
            outcome["applied"].append("D2")
        if d1_fired:
            outcome["applied"].append("D1")
        # Recompute the project_mgmt gate with upstream-corrected recalls.
        source = (d2.get("corrected_scores") if d2_fired else None) or (grade.get("scores") or {})
        details = (d2.get("corrected_details") if d2_fired else None) or (grade.get("details") or {})
        thresholds = grade.get("thresholds") or {}
        counts = {
            cat: sum(1 for v in (details.get(cat) or {}).values() if v.get("matched"))
            for cat in ("workstreams", "risks", "decisions", "milestones")
        }
        recalls_and_sections_ok = (
            counts["workstreams"] >= thresholds.get("min_workstreams", 4)
            and counts["risks"] >= thresholds.get("min_risks", 3)
            and counts["decisions"] >= thresholds.get("min_decisions", 3)
            and counts["milestones"] >= thresholds.get("min_milestones", 3)
            and len(source.get("sections_present") or (grade.get("scores") or {}).get("sections_present") or []) >= 3
        )
        stored_length_ok = (
            (grade.get("scores") or {}).get("word_count", 10 ** 9)
            <= thresholds.get("max_word_count", 700)
        )
        if d2_fired:
            # The real length gate stays in force for the verdict correction; D1 never
            # silently upgrades a verdict -- its invalidation is reported separately.
            outcome["corrected_verdict"] = (
                "PASS" if (recalls_and_sections_ok and stored_length_ok) else "FAIL"
            )
        if d1_fired:
            outcome["verdict_without_length_gate"] = (
                "PASS" if recalls_and_sections_ok else "FAIL"
            )
        return outcome

    if d1_fired:
        outcome["applied"].append("D1")
        # D1 `applies` already established every non-length gate passed.
        outcome["verdict_without_length_gate"] = "PASS"
        return outcome

    return outcome


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def load_frozen_rows(dataset: Path) -> list[dict]:
    with dataset.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def process(args) -> dict:
    checkout_root = args.checkout_root.resolve()
    rows = load_frozen_rows(args.dataset)
    rule_ids = None if args.pm_rules == "all" else {r.strip() for r in args.pm_rules.split(",") if r.strip()}

    results = []
    skipped = {"quarantined": 0, "no_grade_json": 0, "unreadable_grade_json": 0}
    invariant_checked = 0
    invariant_violations = []
    post_freeze_divergence = []

    for row in rows:
        cell, repo = row["cell"], row["repo"]
        if cell.startswith("_"):
            skipped["quarantined"] += 1
            continue
        repo_root = checkout_root / repo
        cell_dir = repo_root / "logs" / cell
        grade_path = cell_dir / "grade.json"
        if not grade_path.is_file():
            skipped["no_grade_json"] += 1
            continue
        try:
            grade = json.loads(grade_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            skipped["unreadable_grade_json"] += 1
            continue

        frozen_graded = row.get("graded") == "1"
        disk_verdict = grade.get("verdict")
        if disk_verdict != row.get("verdict"):
            # The corpus is still being written.  Anything that changed since the freeze
            # is quarantined from headline counts, never silently absorbed.
            post_freeze_divergence.append({
                "repo": repo, "cell": cell,
                "frozen_verdict": row.get("verdict"), "on_disk_verdict": disk_verdict,
                "frozen_graded_flag": row.get("graded"),
            })

        d1 = correct_word_gate(cell_dir, grade)
        try:
            d2 = correct_project_mgmt(cell_dir, repo_root, grade, rule_ids)
        except FileNotFoundError:
            d2 = None
        d3 = correct_triage(repo_root, grade)

        outcome = compose_verdict(grade, d1, d2, d3)
        applied = outcome["applied"]
        corrected_verdict = outcome["corrected_verdict"]

        # INVARIANT: all three corrections are strictly leniency.  Checked over every
        # graded cell, including cells no defect touched, and over BOTH output verdict
        # fields (a gate waiver can only relax, never tighten, so it is held to the
        # same bar).
        if disk_verdict in ("PASS", "FAIL"):
            invariant_checked += 1
            for field, value in (
                ("corrected_verdict", corrected_verdict),
                ("verdict_without_length_gate", outcome["verdict_without_length_gate"]),
            ):
                if disk_verdict == "PASS" and value == "FAIL":
                    invariant_violations.append({"repo": repo, "cell": cell,
                                                 "original": disk_verdict,
                                                 "field": field,
                                                 "corrected": value,
                                                 "applied": applied})

        if not applied:
            continue

        payload = {
            "schema_version": SCHEMA_VERSION,
            "cell": cell,
            "repo": repo,
            "family": row.get("family"),
            "task": grade.get("task"),
            "identity": {
                "model": row.get("model"),
                "quant": row.get("quant"),
                "mode": row.get("mode"),
                "regime": row.get("regime"),
                "arm": row.get("arm"),
                "replicate": row.get("replicate"),
                "source": FROZEN_DATASET_NOTE,
            },
            "original_verdict": disk_verdict,
            "defects_applied": applied,
            "frozen_dataset": {
                "graded_at_freeze": frozen_graded,
                "verdict_at_freeze": row.get("verdict"),
                "matches_on_disk": disk_verdict == row.get("verdict"),
            },
            "evidence": {k: v for k, v in
                         (("D1", d1), ("D2", d2), ("D3", d3)) if v is not None},
            "grade_json_sha256": sha256_file(grade_path),
            "policy": (
                "grade.json, task briefs and ground truth are immutable run evidence; "
                "this overlay modifies no run artifact and no raw verdict"
            ),
        }
        # `corrected_verdict` exists ONLY where a D2/D3 verdict correction fired.
        if corrected_verdict is not None:
            payload["corrected_verdict"] = corrected_verdict
            payload["verdict_changed"] = corrected_verdict != disk_verdict
        # D1 is recorded as a gate invalidation, never as a verdict.
        if outcome["gate_invalidated"]:
            payload["gate_invalidated"] = True
            payload["verdict_without_length_gate"] = outcome["verdict_without_length_gate"]
            payload["gate_invalidated_meaning"] = (
                "the original FAIL is attributable solely to the length gate, where two "
                "reasonable word counters disagree across the threshold; read this cell "
                "as NOT A VALID FAIL, not as a verified PASS "
                "(grader-defects doc, D1 correction limits)"
            )
        results.append({
            "row": row, "payload": payload, "cell_dir": cell_dir,
            "applied": applied, "original": disk_verdict, "corrected": corrected_verdict,
            "gate_invalidated": outcome["gate_invalidated"],
            "verdict_without_length_gate": outcome["verdict_without_length_gate"],
            "frozen_graded": frozen_graded,
        })

    return {
        "results": results,
        "skipped": skipped,
        "invariant_checked": invariant_checked,
        "invariant_violations": invariant_violations,
        "post_freeze_divergence": post_freeze_divergence,
        "rows_total": len(rows),
        "rule_ids": sorted(rule_ids) if rule_ids else "all upstream rules",
    }


def summarise(state: dict) -> dict:
    """Per-defect counts.  D1 counts GATE INVALIDATIONS, not verdict changes -- the two
    are different claims and are kept under different keys so an aggregator cannot sum
    them into one number by accident."""
    frozen = [r for r in state["results"] if r["frozen_graded"]]
    by_defect: dict[str, dict[str, int]] = {}
    for r in frozen:
        for d in r["applied"]:
            model = r["row"]["model"]
            if d == "D1":
                slot = by_defect.setdefault(d, {"3.6": 0, "3.8": 0, "total": 0,
                                                "gate_invalidated_3.6": 0,
                                                "gate_invalidated_3.8": 0,
                                                "gate_invalidated_total": 0})
                slot[model] = slot.get(model, 0) + 1
                slot["total"] += 1
                if r["gate_invalidated"]:
                    slot[f"gate_invalidated_{model}"] = slot.get(f"gate_invalidated_{model}", 0) + 1
                    slot["gate_invalidated_total"] += 1
            else:
                slot = by_defect.setdefault(d, {"3.6": 0, "3.8": 0, "total": 0,
                                                "verdict_changed_3.6": 0,
                                                "verdict_changed_3.8": 0,
                                                "verdict_changed_total": 0})
                slot[model] = slot.get(model, 0) + 1
                slot["total"] += 1
                if r["corrected"] is not None and r["corrected"] != r["original"]:
                    slot[f"verdict_changed_{model}"] = slot.get(f"verdict_changed_{model}", 0) + 1
                    slot["verdict_changed_total"] += 1
    return {
        "cells_touched_frozen": len(frozen),
        "cells_touched_including_post_freeze": len(state["results"]),
        "by_defect": by_defect,
    }


def d2_mechanism_report(state: dict) -> dict:
    """Manifest-level record of WHICH text satisfied the upstream adjacency regex, per
    corrected cell.  The rule matches more than contractions, so the matched spans -- not
    the narrative shorthand -- document the mechanism actually applied."""
    spans = []
    patterns = set()
    for r in state["results"]:
        if "D2" not in r["applied"]:
            continue
        d2 = (r["payload"].get("evidence") or {}).get("D2") or {}
        for change in d2.get("changes") or []:
            if change.get("pattern"):
                patterns.add(change["pattern"])
            spans.append({
                "repo": r["row"]["repo"],
                "cell": r["row"]["cell"],
                "item": change.get("item"),
                "matched_span": change.get("matched_span"),
            })
    spans.sort(key=lambda e: (e["repo"], e["cell"], str(e["item"])))
    return {
        "note": (
            "the mechanism actually applied is upstream rule R3, an adjacency regex "
            "(the word legal within 200 characters of a completion term), which matches "
            "strictly more than contractions; matched_span is the exact normalised "
            "report text that satisfied the regex in each corrected cell"
        ),
        "patterns": sorted(patterns),
        "matched_spans": spans,
    }


def print_table(state: dict, summary: dict) -> None:
    print("=" * 78)
    print("MMBT GRADE-CORRECTION OVERLAY  --  DRY RUN (nothing written)")
    print("=" * 78)
    print(f"frozen dataset rows            : {state['rows_total']}")
    print(f"skipped, quarantined           : {state['skipped']['quarantined']}")
    print(f"skipped, no grade.json on disk : {state['skipped']['no_grade_json']}")
    print(f"skipped, unreadable grade.json : {state['skipped']['unreadable_grade_json']}")
    print(f"D2 upstream rules active       : {state['rule_ids']}")
    print()
    print(f"cells corrected (frozen-graded) : {summary['cells_touched_frozen']}")
    print(f"cells corrected (incl. post-freeze) : {summary['cells_touched_including_post_freeze']}")
    print()
    header = f"{'defect':<8}{'3.6':>8}{'3.8':>8}{'total':>8}   {'effect (3.6/3.8/tot)':>40}"
    print(header)
    print("-" * len(header))
    for defect in sorted(summary["by_defect"]):
        s = summary["by_defect"][defect]
        if "gate_invalidated_total" in s:
            effect = (f"{s['gate_invalidated_3.6']}/{s['gate_invalidated_3.8']}"
                      f"/{s['gate_invalidated_total']} gates invalidated")
        else:
            effect = (f"{s['verdict_changed_3.6']}/{s['verdict_changed_3.8']}"
                      f"/{s['verdict_changed_total']} verdicts changed")
        print(f"{defect:<8}{s['3.6']:>8}{s['3.8']:>8}{s['total']:>8}   {effect:>40}")
    print()
    print("--- per-family breakdown (frozen-graded cells only) ---")
    print("    vchg = verdict corrections (D2/D3); ginv = length-gate invalidations (D1)")
    fam: dict[tuple, dict] = {}
    for r in state["results"]:
        if not r["frozen_graded"]:
            continue
        key = (r["row"]["family"], ",".join(r["applied"]))
        slot = fam.setdefault(key, {"3.6": 0, "3.8": 0,
                                    "vchg36": 0, "vchg38": 0, "ginv36": 0, "ginv38": 0})
        suffix = "36" if r["row"]["model"] == "3.6" else "38"
        slot[r["row"]["model"]] += 1
        if r["corrected"] is not None and r["corrected"] != r["original"]:
            slot["vchg" + suffix] += 1
        if r["gate_invalidated"]:
            slot["ginv" + suffix] += 1
    head = (f"{'family':<14}{'defects':<10}{'n3.6':>6}{'n3.8':>6}"
            f"{'vchg3.6':>9}{'vchg3.8':>9}{'ginv3.6':>9}{'ginv3.8':>9}")
    print(head)
    print("-" * len(head))
    for key in sorted(fam):
        s = fam[key]
        print(f"{key[0]:<14}{key[1]:<10}{s['3.6']:>6}{s['3.8']:>6}"
              f"{s['vchg36']:>9}{s['vchg38']:>9}{s['ginv36']:>9}{s['ginv38']:>9}")
    print()
    print("--- leniency invariant ---")
    print(f"graded cells checked for PASS -> FAIL : {state['invariant_checked']}")
    print(f"violations (PASS -> FAIL)             : {len(state['invariant_violations'])}")
    for v in state["invariant_violations"]:
        print("   VIOLATION:", v)
    print()
    print("--- post-freeze corpus drift (excluded from headline counts) ---")
    print(f"cells whose on-disk verdict differs from the frozen dataset : "
          f"{len(state['post_freeze_divergence'])}")
    for d in state["post_freeze_divergence"]:
        print(f"   {d['repo']}/{d['cell']}: frozen={d['frozen_verdict']!r} "
              f"disk={d['on_disk_verdict']!r} graded_flag={d['frozen_graded_flag']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    ap.add_argument("--checkout-root", type=Path, default=DEFAULT_CHECKOUT_ROOT)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the summary table and write nothing at all")
    ap.add_argument("--in-place", action="store_true",
                    help="write true grade.corrected.json siblings into the checkouts "
                         "instead of the staging mirror (still cannot touch protected paths)")
    ap.add_argument("--pm-rules", default="R3",
                    help="upstream project-management rules to apply: 'R3' (default, the "
                         "only rule this PR verified) or 'all'")
    ap.add_argument("--json-summary", type=Path, default=None)
    args = ap.parse_args()

    state = process(args)
    summary = summarise(state)

    if args.dry_run:
        print_table(state, summary)
    else:
        payloads = []
        for r in state["results"]:
            text = canonical_json(r["payload"])
            payloads.append(text)
            if args.in_place:
                out = r["cell_dir"] / "grade.corrected.json"
            else:
                out = (args.output_root / r["row"]["repo"] / "logs"
                       / r["row"]["cell"] / "grade.corrected.json")
            guarded_write(out, text)
        digest = hashlib.sha256("".join(sorted(payloads)).encode("utf-8")).hexdigest()
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overlay_digest": digest,
            "note": "overlay_digest excludes generated_at and is stable across runs",
            "frozen_dataset": str(args.dataset),
            "frozen_dataset_sha256": sha256_file(args.dataset),
            "frozen_dataset_stamp": FREEZE_STAMP,
            "summary": summary,
            "d2_mechanism": d2_mechanism_report(state),
            "invariant_checked": state["invariant_checked"],
            "invariant_violations": state["invariant_violations"],
            "post_freeze_divergence": state["post_freeze_divergence"],
            "skipped": state["skipped"],
        }
        guarded_write(args.output_root / "manifest.json", canonical_json(manifest))
        print(json.dumps({"written": len(payloads), "overlay_digest": digest}, indent=2))

    if args.json_summary:
        guarded_write(args.json_summary, canonical_json({
            "summary": summary,
            "invariant_checked": state["invariant_checked"],
            "invariant_violations": state["invariant_violations"],
            "post_freeze_divergence": state["post_freeze_divergence"],
            "skipped": state["skipped"],
            "detail": [
                {"repo": r["row"]["repo"], "cell": r["row"]["cell"],
                 "family": r["row"]["family"], "model": r["row"]["model"],
                 "applied": r["applied"], "original": r["original"],
                 "corrected": r["corrected"],
                 "gate_invalidated": r["gate_invalidated"],
                 "verdict_without_length_gate": r["verdict_without_length_gate"],
                 "frozen_graded": r["frozen_graded"]}
                for r in state["results"]
            ],
        }))

    return 1 if state["invariant_violations"] else 0


if __name__ == "__main__":
    sys.exit(main())

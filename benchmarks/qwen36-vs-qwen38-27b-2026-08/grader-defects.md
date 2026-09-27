# Grader defects in this comparison, and the corrections applied

This document reports three defects **in MMBT's own graders**, found while grading the
Qwen3.6-27B vs Qwen3.8-27B comparison. Two of them (D1, D3) change the direction of a
family-level result. One of them (D2) was already known to this repository and already
fixed here — but the fix was hardcoded to a different model's cell names and so never ran
on these campaigns. That is disclosed in full below rather than buried, because it is the
first thing a reviewer will find.

Nothing in the run evidence was edited. `grade.json`, task briefs and ground-truth files
are immutable; corrections ship as a separate overlay, following the convention the
repository already states in `tooling/correct_gemma4_project_mgmt_grades.py:165`:

> `"policy": "immutable grade.json files remain raw evidence; this overlay changes no run artifact or raw verdict"`

---

## Provenance and evidence rules

| Item | Value |
| --- | --- |
| Frozen dataset | `/home/michael/mmbt-frozen-dataset-v2.csv` (freeze #2), 802 rows, frozen 2026-08-16T14:23:09Z |
| Frozen dataset sha256 | `d2ed0beca5b68e9ca63788e452235f23a299af06639893f558bef19f784cf018` |
| Supersedes | freeze #1, `mmbt-frozen-dataset.csv`, 746 rows, 2026-08-16T11:49:14Z |
| Measurements in this document read at | 2026-08-16T14:30Z – 14:50Z |
| Cells used for every count below | the 733 of 802 rows with `graded == 1` |

Every count in this document is restricted to frozen-dataset rows with `graded == 1`.
That restriction is not cosmetic. **The corpus was still being written while the freeze-1
analysis ran** — two reads of the `p2_triage` family eleven minutes apart returned 58 and
then 59 scored cells, because a `grade.json` for a cell freeze #1 marked `graded=0`
appeared on disk in between. Freeze #2 closes that gap: every campaign process is stopped,
in-flight cells are quarantined out of the extract, and the overlay manifest's
`post_freeze_divergence` ledger is empty — the on-disk verdict agrees with the frozen
verdict for every one of the 733 graded rows. The corpus behind this document is static.
Cell identity, model and sampler are taken verbatim from the frozen dataset and never
recomputed from directory names.

The graders are **byte-identical across all seven checkouts on this host** — the five
Qwen checkouts (`mmbt-q38-card`, `mmbt-qwen38-eaaa8ca`, `mmbt-q36-card`,
`mmbt-qwen36-compare`, `mmbt-q38-q8`) and the two prior campaign trees
(`bench-gemma4-31b-q4`, `bench-deepseek-v4-flash-0731`). This is what makes the
"previously published results" section at the end unavoidable.

| File | sha256 |
| --- | --- |
| `tooling/graders/phase3_project_mgmt_grade.py` | `e1c3a9190e6d19cffd76734c8c922450b22d674bd5fd2db052fef31f91777bca` |
| `tooling/graders/phase3_doc_synthesis_grade.py` | `8c117c0a3bfec94a91f94e49bb5b4281a458bcc4a650e9ae86e2450f0f5cac0a` |
| `tooling/graders/phase3_business_memo_grade.py` | `691c5c6cec0f3bbf2fc86e80c47dd3fc2bde4873dc630297a0aea13edd548d7b` |
| `tooling/graders/phase3_writing_editing_grade.py` | `a3461f31be9d24cc1c5132fff4bff96a27af77af2457dad839ef5498afba8f56` |
| `tooling/graders/phase2_triage_grade.py` | `ea3eebcf6a2fc085276e555f2cb1a54239e1dc9286bac3cb2300f01929b855a1` |
| `tooling/graders/ground_truth/phase2_triage.json` | `6ca3763f32abfe3a5b8dfa56662c9083f91f81c2c3d06d3117bfb974367669d1` |
| `tooling/tasks/task_triage.md` | `d92feeb839dbb8850d6447c6c821fc4c74ae68cc53c4917438f8a10f9531292b` |
| `tooling/correct_gemma4_project_mgmt_grades.py` | `86eeec68b6c7114fb0672566220938e35fa605cd1b89ac4b0863f7cfe305f581` |

---

## Summary

| | D1 word-gate tokenizer mismatch | D2 `p3_pm` keyword literalism | D3 `p2_triage` brief contradiction |
| --- | --- | --- | --- |
| Families hit | `p3_business`, `p3_doc`, `p3_writing` | `p3_pm` | `p2_triage` |
| Cells corrected | 62 (23 of 3.6, 39 of 3.8) | 39 (33 of 3.6, 6 of 3.8) | 64 (38 of 3.6, 26 of 3.8) |
| Verdict changes | 62 gate invalidations (23 / 39) | 36 (31 of 3.6, 5 of 3.8) | 24 (21 of 3.6, 3 of 3.8) |
| Direction | favours 3.6 uncorrected | favours 3.8 uncorrected | favours 3.8 uncorrected |
| Honest post-correction status | **gate is not a valid discriminator** | family saturates; not a discriminator | family saturates; not a discriminator |

The 3.8 columns include the Q8_0 control's graded cells (freeze #2 admits 8): one Q8_0
cell each in the D2 and D3 counts. The Q8_0 `p3_business` and `p3_doc` FAILs are length
FAILs that stand under **both** counters, so D1 does not correct them.

Read the last row carefully. In all three cases the correct conclusion is *"this gate
does not measure what the benchmark claims it measures"*, not *"the other model actually
won"*. Two of the three corrected families end at a ceiling where every cell of both
models passes, which is exactly as uninformative as the uncorrected result — just
uninformative in a way that is visible.

---

## D1 — Word-gate tokenizer mismatch

### The grader source

Four phase-3 graders let a word count decide the verdict, and all four count words with
the same Python regex.

`tooling/graders/phase3_doc_synthesis_grade.py`

```
48:    word_count = len(re.findall(r"\b\w+\b", brief))
...
68:    word_limit = 700
70:        "PASS" if (captured >= coverage_threshold and word_count <= word_limit)
```

`tooling/graders/phase3_business_memo_grade.py`

```
73:    word_count_memo = len(re.findall(r"\b\w+\b", memo.read_text()))
...
113:    word_limit = 700
115:        "PASS" if (bias_recall >= bias_threshold and stance_pushback and word_count_memo <= word_limit)
```

`tooling/graders/phase3_writing_editing_grade.py`

```
17: def word_count(text: str) -> int:
18:     return len(re.findall(r"\b\w+\b", text))
...
92:     wc = word_count(text)
93:     max_words = brief.get("max_words", 9999)
...
110:        "verdict": "PASS" if (required_pass and prohibited_pass and wc <= max_words) else "FAIL",
```

`tooling/graders/phase3_project_mgmt_grade.py`

```
64:    word_count = len(re.findall(r"\b\w+\b", text))
...
100:        and word_count <= 700
```

A fifth grader, `phase3_market_research_grade.py:38`, computes `rec_words` with the same
regex but never gates on it — it only reports it as
`"recommendation_word_count"` (line 86). It is therefore not affected and is excluded
from every D1 count below.

### What the models counted with

The task briefs impose the ceiling without ever defining how a word is counted:

```
task_doc_synthesis.md:8   1. Be **at most 700 words** — this is for a partner who has 5 minutes.
task_business_memo.md:9   Produce **a 1-page memo** (≤700 words) for the executive committee with:
task_writing_editing.md:20  - **Stay within word limits.** The max_words per audience is in `audience_briefs.json`. Use it as a hard ceiling.
```

Given a Linux VM and no definition, both models reached for the obvious tool. Across the
293 graded phase-3 cells, the transcript contains a literal `wc -w` invocation in:

| Model | Cells with a `wc -w` call | Graded phase-3 cells | Share |
| --- | --- | --- | --- |
| 3.6 | 159 | 185 | 85.9% |
| 3.8 | 95 | 108 | 88.0% |

Restricted to the four length-gated families the shares are higher still: 152 of 152
Qwen3.6 and 93 of 95 Qwen3.8 graded length-gated transcripts contain a `wc -w` call.

Typical call, taken verbatim from `p3_business_qwen36-nothink-offspec_v1`: `wc -w /workspace/memo.md`.

So the benchmark set a hard threshold on a quantity it did not define, the models
measured that quantity with the standard tool, and the grader measured it with a
different tool.

### Proof that the two counters disagree by more than the margin

Mechanism, measured on `p3_doc_qwen36-think-offspec_v1`'s `brief.md` (ceiling 700):

```
grader regex \b\w+\b : 707   ->  FAIL
shell wc -w          : 698   ->  under the cap
```

The 9-word gap decomposes exactly:

- 25 `wc -w` tokens contain no word character at all — pure markdown punctuation that
  `wc` counts as words and the regex does not: `—` ×7, `---` ×6, `##` ×6, `-` ×5, `#` ×1.
- 34 `wc -w` tokens are split into more than one word by `\b\w+\b`: `Follow-On` → `Follow`,
  `On`; `well-funded` → `well`, `funded`; `product-market` → `product`, `market`;
  `($4.2M` → `4`, `2M`. That adds 34 words.
- 698 − 25 + 34 = 707. Exact.

Across all 364 phase-3 deliverables extracted from `workspace_final.tar.gz` for the
graded cells, the two counters disagree in **both** directions: the regex returns the
larger count for 259 of 364, `wc -w` returns the larger count for 78 of 364, and they tie
for 27 of 364. The divergence ranges from −20.95% to +8.70% of the `wc -w` count, median
+1.95%. Documents heavy in markdown tables swing the other way, because every `|` is a
word to `wc`.

**Neither counter is ground truth.** `wc -w` counting `|`, `##` and `---` as words is not
more correct than a regex splitting `product-market` into two words. Both are defensible;
they are simply different, and they differ by more than the margin at issue.

### Blast radius

A cell is a **length-attributable FAIL** if the grader returned FAIL, at least one
deliverable exceeded its ceiling by the grader's regex, and every non-length gate passed
(facts captured, bias recall and stance, required/prohibited content — so that removing
the length gate alone would flip the verdict).

| | 3.6 | 3.8 | total |
| --- | --- | --- | --- |
| Length-attributable FAILs | 24 | 47 | 71 |
| …of which under **every** ceiling by `wc -w` | 23 | 39 | **62** |
| …of which still over by `wc -w` (genuinely long) | 1 | 8 | 9 |

The 3.8 column includes the Q8_0 control's two length FAILs (`p3_business`, `p3_doc`),
both of which sit in the still-over row. By family, the 71: `p3_doc` 26, `p3_writing` 24,
`p3_business` 21. The grader's stored word count reproduced exactly from the archived
deliverable in 71 of 71 cases, so the recount is measuring the same bytes the grader
measured. The full cell-by-cell table with both counts is in Appendix A.

Family pass rates under three treatments of the length gate (graded cells only):

| Family | Model | n | Raw (regex gate) | If `wc -w` were the gate | Length gate removed |
| --- | --- | --- | --- | --- | --- |
| `p3_business` | 3.6 | 38 | 35 (92.1%) | 37 (97.4%) | 38 (100.0%) |
| `p3_business` | 3.8 | 23 | 4 (17.4%) | 17 (73.9%) | 22 (95.7%) |
| `p3_doc` | 3.6 | 38 | 28 (73.7%) | 38 (100.0%) | 38 (100.0%) |
| `p3_doc` | 3.8 | 25 | 9 (36.0%) | 23 (92.0%) | 25 (100.0%) |
| `p3_writing` | 3.6 | 38 | 11 (28.9%) | 22 (57.9%) | 22 (57.9%) |
| `p3_writing` | 3.8 | 21 | 8 (38.1%) | 20 (95.2%) | 21 (100.0%) |
| **all three** | **3.6** | **114** | **74 (64.9%)** | **97 (85.1%)** | **98 (86.0%)** |
| **all three** | **3.8** | **69** | **21 (30.4%)** | **60 (87.0%)** | **68 (98.6%)** |

(The one `p3_business` 3.8 cell that does not pass even with the length gate removed is a
`MISSING_OUTPUT` verdict — no memo in the archived workspace — not a gate effect. The 3.8
rows include the Q8_0 control's graded phase-3 cells.)

This is the reason D1 matters. Under the shipped grader these three families read as a
34-point win for 3.6 (64.9% vs 30.4%). Swap in the other equally-defensible counter and
they read as a 2-point win for 3.8 (85.1% vs 87.0%). The gate is deciding the headline.

`p3_pm` is unaffected: its ceiling is 700 and the largest regex word count across all 64
graded `p3_pm` cells is 576, so the length gate never binds there.

### Correction applied, and its limits

The overlay marks the 62 cells that are over by the grader's regex and under by `wc -w`,
records both counts, both file hashes, and the `wc -w` locale used
(`LC_ALL=C.UTF-8`, matching the sandbox image), and records
`gate_invalidated: true` together with `verdict_without_length_gate: "PASS"` —
deliberately **not** a `corrected_verdict`, which the overlay reserves for the D2/D3
verdict corrections — so that downstream aggregation must name its treatment of these
cells rather than silently counting them as passes.

**The overlay's `verdict_without_length_gate: "PASS"` is not a claim that these
deliverables complied with the word limit.** It is a claim that the FAIL is not
defensible. The honest statement is:

> For these 62 cells the verdict is *counter-dependent*. Two reasonable word counters
> disagree across the threshold. MMBT's length gate is not a valid discriminator at these
> margins and should not carry weight in any headline comparison until the benchmark
> defines its tokenizer and states it in the brief.

Anyone aggregating this overlay should read the 62 as "not a valid FAIL", not as "a
verified PASS", and should prefer the "length gate removed" column above when comparing
models. The 9 cells that are over by both counters remain FAIL and are not touched.

Limits, stated plainly:

- This does not fix the benchmark. It documents that one gate was unmeasurable as
  specified. The durable fix is upstream: define the counter in the brief, or replace the
  hard threshold with a soft penalty, and re-run.
- `wc -w` behaviour is locale-dependent; the overlay pins `C.UTF-8` and verified the
  shell result against a pure-Python `str.split()` recount for every deliverable.
- The 62 correction does not disturb non-length failures. `p3_writing` for 3.6 still fails
  16 of 38 cells on required/prohibited content, which is why its "length gate removed"
  column stops at 57.9% rather than reaching 100%.

---

## D2 — `p3_pm` keyword literalism (and the fix this repo already had)

### The grader source

`tooling/graders/phase3_project_mgmt_grade.py`

```
17: def normalize(s: str) -> str:
18:     return re.sub(r"\s+", " ", s.lower())
...
31: RISK_KEYWORDS = {
...
34:     "R3": ["legal unresponsive", "legal silent", "legal hasn't", "blocking on legal"],
...
70:             hit = next((kw for kw in keywords if normalize(kw) in norm), None)
...
97:         and risk_recall >= 3
```

`normalize` lowercases and collapses whitespace. It does not expand or contract
apostrophes. So R3 recognises `legal hasn't` and does not recognise `legal has not`.

### The model output it misses

`p3_pm_qwen36-nothink-card_v2`, `status_report.md` line 22 — verbatim:

```
| **High** | Private-beta contracts unsigned | Legal has not responded to draft [wk6] |
```

`p3_pm_qwen36-nothink-card_v8`, `status_report.md` line 22 — byte-identical to v2
(both lines hash to `d34282e4e207623e234fb9731c144e41`):

```
| **High** | Private-beta contracts unsigned | Legal has not responded to draft [wk6] |
```

`p3_pm_qwen36-nothink-card_v4`, `status_report.md` line 22:

```
| **High** | Private-beta contracts unsigned | Legal hasn't responded to draft [wk6] |
```

Same table, same row, same risk, same evidence citation. The only difference is the
contraction.

### The natural experiment

These three cells are the same model at the same sampler point
(3.6, no-think, `T1/p0.95/pp0`, `mmbt-q36-card`), and their graded scores are identical on
every gate except R3:

| Cell | line-22 phrasing | R3 | risk_recall | workstream | decision | milestone | sections | word_count (cap 700) | **verdict** |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `p3_pm_qwen36-nothink-card_v2` | `Legal has not responded` | ✗ | **2/6** | 6/6 | 4/4 | 5/5 | 4/4 | 379 | **FAIL** |
| `p3_pm_qwen36-nothink-card_v8` | `Legal has not responded` | ✗ | **2/6** | 6/6 | 4/4 | 5/5 | 4/4 | 388 | **FAIL** |
| `p3_pm_qwen36-nothink-card_v4` | `Legal hasn't responded` | ✓ (`"legal hasn't"`) | **3/6** | 6/6 | 4/4 | 5/5 | 4/4 | 388 | **PASS** |

The threshold is `risk_recall >= 3` (line 97). The apostrophe is the entire difference
between PASS and FAIL. This is not a judgement call about whether the model identified the
risk — all three identified it, in the same words, in the same row of the same table.

The whole family turns on this gate: raw `risk_recall` is exactly `2/6` for all 39 FAIL
cells and `>= 3/6` for all 25 PASS cells, across 64 graded cells. No `p3_pm` cell fails on
any other gate.

### The fix was already in this repository, unapplied

`tooling/correct_gemma4_project_mgmt_grades.py` — present, unit-tested, and byte-identical
in all seven checkouts — already encodes exactly this correction:

```
22:    "R3": {
23:        "description": "legal/private-beta contract delay uses an equivalent non-contracted phrase",
24:        "patterns": [
25:            r"\blegal\b.{0,200}\b(?:has\s+not|not\s+yet\s+responded|sign[ -]?off|approval|unresponsive|silent|delay|contract)\b",
26:        ],
27:    },
```

`tooling/test_correct_gemma4_project_mgmt_grades.py` covers it —
`test_semantic_equivalents_correct_only_the_known_lexical_misses` asserts R2, R3,
`D3_mobile` and `D4_option_b`; the suite passes (4 passed).
`tooling/deployments/gemma4-31b-q4-tower2/README.md:170-178` documents the defect in
prose, naming the exact miss:

> "The raw project-management grader searches for a few contiguous phrases and misses
> semantically exact wording such as "Maevia … push back," "Legal has not yet responded,"
> hyphenated "web-responsive," and "private beta (3-5 customers).""

It never ran on the Qwen campaigns for one reason — line 133 enumerates cells by a
hardcoded name pattern:

```
133:        name = f"p3_pm_gemma4-31b-q4_v{replicate}"
```

So a correction this project had already written, tested, documented and shipped for the
Gemma4 campaign silently did not apply to any cell whose name did not start with
`p3_pm_gemma4-31b-q4_`. This is disclosed here rather than buried because it is the
single most damaging thing a reviewer could find unaided, and because it points at a
process defect worse than the grader bug: a correction whose scope is a filename prefix.

### Blast radius

Raw R3 matched in only 24 of 64 graded `p3_pm` cells. The overlay's R3 rule fires on 39 of
64 (the 40 raw non-matches minus one the regex also does not reach).

| | 3.6 | 3.8 | total |
| --- | --- | --- | --- |
| Graded `p3_pm` cells | 38 | 26 | 64 |
| Raw PASS | 4 (10.5%) | 21 (80.8%) | 25 |
| R3 overlay fires | 33 | 6 | 39 |
| PASS after R3 correction | 35 (92.1%) | 26 (100.0%) | 61 |
| Verdict changes | 31 | 5 | **36** |

(The 3.8 column includes the single graded Q8_0 `p3_pm` cell, whose raw FAIL is also an
R3 literalism and is corrected to PASS.) Uncorrected, `p3_pm` reads as a 70-point rout
for 3.8 (10.5% vs 80.8%). Corrected, it is 92.1% vs 100.0%. The uncorrected result was
measuring which model contracts its verbs.

### Correction applied, and its limits

The overlay reuses the repository's existing module rather than reimplementing it — it
imports `read_archived_report` and `apply_correction` from
`tooling/correct_gemma4_project_mgmt_grades.py` (sha256
`86eeec68b6c7…`) and changes exactly one thing: cell selection is driven from the frozen
dataset instead of `build()`'s hardcoded `p3_pm_gemma4-31b-q4_v{n}` names. Report text is
read from `workspace_final.tar.gz:./status_report.md`, never from a live workspace.

**Only the R3 rule is activated.** The upstream module also ships R2, `D3_mobile` and
`D4_option_b`. They are deliberately left inactive, and that decision must be disclosed
because it is visible in the overlay records (`"active_rules": ["R3"]`):

- Only R3 has a decisive natural experiment. R2's keyword bundle
  (`["maevia push", "maevia push-back", "maevia pushback", "expectations gap"]`) raw-matched
  in just 2 of 64 cells, and the upstream replacement pattern
  (`\bmaevia\b.{0,240}\b(?:push(?:ed)?[ -]?back|fallout|promis(?:e|ed)\s+ga|private[ -]?beta)\b`)
  fires on 64 of 64. A rule that fires on 100% of a family is a rewrite of the rubric, not
  a correction of a false negative, and it deserves its own scrutiny rather than a free
  ride on R3's evidence.
- Activating all four upstream rules takes `p3_pm` to **64 of 64 PASS** for both models —
  3 more verdict changes than R3 alone. That is a ceiling, and a ceiling measures nothing.

Limits:

- Even with R3 alone, corrected `p3_pm` is 35/38 vs 26/26. That is close enough to
  saturation that `p3_pm` should not carry weight as a discriminator in this comparison in
  either direction. Report it, do not lean on it.
- The correction rescues a keyword match; it does not verify that the model's risk
  description is *good*. The grader's hand-rating fields
  (`structure_quality_1to5`, `fabrication_count`, `owner_accuracy_0to6`) are `null` in every
  cell, so no qualitative check backs any `p3_pm` verdict, corrected or raw.
- R1 and R6 remain unmatched in most cells and are not corrected. No claim is made that
  the corrected `risk_recall` is the true recall — only that the R3 component was a
  verified false negative.

---

## D3 — `p2_triage` brief / ground-truth contradiction

### The contradiction

`tooling/tasks/task_triage.md:27`, in the closed urgency vocabulary the brief requires the
model to use:

```
- `n/a` — for noise/spam where urgency doesn't apply
```

`tooling/graders/ground_truth/phase2_triage.json`, the three tickets the same ground truth
categorises as `spam-or-noise`:

```
23:    "004": {"category": "spam-or-noise", "urgency": "low", "notes": "fictitious 'free Pixar collectables' premise; no such program"},
28:    "009": {"category": "spam-or-noise", "urgency": "low", "notes": "obvious phishing email impersonating account-security"},
40:    "021": {"category": "spam-or-noise", "urgency": "low", "notes": "affiliate-link blog-hosting spam"},
```

The ground truth contains **zero** `n/a` urgency labels across all 30 tickets
(distribution: `normal` 17, `urgent` 7, `low` 6). The value the brief defines for
noise/spam is never the answer.

The grader compares by exact string equality and applies a hard threshold:

`tooling/graders/phase2_triage_grade.py`

```
53:        if a_urg == gt_urg:
...
73:     urg_threshold = 0.70  # 70% urgency accuracy (more subjective)
...
80:             and (urg_accuracy or 0) >= urg_threshold
```

### Proof that it is a defect, not a judgement call

Of the 64 graded `p2_triage` cells, **64 of 64 answered `n/a` for all three spam
tickets** — every replicate of both models, both thinking modes, every sampler point, and
the Q8_0 control cell. Zero cells answered `low`. Every cell therefore lost exactly
3/30 = 0.100 of urgency accuracy for following the brief, against a 0.700 threshold.

A defect that penalises 100% of cells identically for complying with the written
instructions is not a discrimination signal; it is a constant subtracted from every score
before it is compared to a threshold.

### A second contradiction in the same family, in the same direction

A reviewer checking the error lists will find this, so it is stated here. Ticket 029 is an
extortion email (`"Pay $50,000 in BTC or I post them on twitter"`). The brief,
`tooling/tasks/task_triage.md:66`:

```
- **Be skeptical of obvious noise.** Phishing emails impersonating "Account Security
  Team," extortion threats, fictitious-premise requests ("free collectables"),
  affiliate-link spam — these are `spam-or-noise`, not real categories.
```

(reflowed for width; the source is one line). The ground truth:
`"029": {"category": "security-incident", "urgency": "urgent", ...}`.

All 64 of 64 cells classified 029 as `spam-or-noise` — exactly as instructed — and all 64
called its urgency `n/a`. It is the only universal category error in the family. So a
second brief-versus-ground-truth conflict costs every cell a further 1/30 = 0.033 of
category accuracy and 1/30 = 0.033 of urgency accuracy. **The overlay does not credit
029**, because unlike the spam trio there is a genuine substantive reading in which an
extortion threat is a security incident; the brief and the rubric simply disagree about
it. It is disclosed rather than corrected.

### Blast radius

| | 3.6 | 3.8 | total |
| --- | --- | --- | --- |
| Graded `p2_triage` cells | 38 | 26 | 64 |
| Answered `n/a` on all three spam tickets | 38 | 26 | **64** |
| Raw PASS | 17 (44.7%) | 23 (88.5%) | 40 |
| PASS after crediting `n/a` | 38 (100.0%) | 26 (100.0%) | 64 |
| Verdict changes | 21 | 3 | **24** |

(The 3.8 column includes the single graded Q8_0 triage cell, a raw PASS at urgency 0.733.)
The apparent 44-point gap in 3.8's favour is an artefact of a constant 0.100 penalty
interacting with a hard threshold: 3.6's failing cells sit at 0.600–0.667 with its passing
tail at 0.733–0.767, while 3.8's cells sit at 0.700–0.800 apart from three at 0.667 — so
the same uniform penalty pushes most of one distribution below the line and leaves the
other above it.

The family has no discriminating power on its other two axes either, which is easy to
verify and worth stating: across all 64 graded cells, `category_accuracy` is **0.867 in
every single cell** and `duplicate_recall` is **1.000 in every single cell**. Zero
variance on both, across both models. Urgency accuracy is the only axis that varies, and
it is the axis the defect corrupts.

### Correction applied, and its limits

The overlay credits the model's `n/a` as correct for tickets 004, 009 and 021 only —
the three the ground truth itself categorises as `spam-or-noise`, which is precisely the
set the brief's line 27 rule names — recomputes urgency accuracy (+0.100), and re-evaluates
the grader's own thresholds. Nothing else in the grade is touched; the grader's arithmetic
was reproduced from the stored error lists before any change was applied.

Limits:

- **The corrected family is 64 of 64 PASS.** It discriminates nothing. Combined with the
  zero variance on category and duplicate recall, the honest reading is that
  `p2_triage` produced no usable signal in this comparison, in either direction. It should
  be reported as such and excluded from any aggregate ship-rate that is meant to compare
  the two models.
- Crediting `n/a` is not a claim that `n/a` is the better label. It is a claim that a
  model cannot be scored down for obeying an instruction the benchmark gave it. The
  durable fix is upstream and is a one-line choice: either add `n/a` to the ground truth
  for the three spam tickets, or delete line 27 from the brief. Until then this family
  measures nothing.
- Ticket 029 is left uncorrected, as described above, which means the residual urgency
  scores still contain a uniform 0.033 penalty of the same kind.

---

## What these defects mean for previously published MMBT results

The graders are byte-identical in `bench-gemma4-31b-q4` and
`bench-deepseek-v4-flash-0731`, and both campaigns ran the affected families
(`p2_triage`, `p3_business`, `p3_doc`, `p3_pm`, `p3_writing`). The defects are therefore
not new; they are newly *found*. Measured directly on those campaigns' run evidence:

**Gemma4-31b-q4 (10 replicates per family)**

| Family | Defect | Finding |
| --- | --- | --- |
| `p2_triage` | D3 | 10 of 10 cells answered `n/a` on all three spam tickets. Crediting them flips **2 of 10** verdicts. Published `p2_triage` numbers for this campaign are wrong by 2/10. |
| `p3_pm` | D2 | 0 of 10 raw PASS. R3 correction alone → 7 of 10; the full published overlay → 10 of 10. This campaign *did* ship the overlay, so its corrected total was already reported — but the raw 0/10 figure, if quoted anywhere without the overlay, is a contraction artefact. |
| `p3_business`, `p3_doc`, `p3_writing` | D1 | 0 length-attributable FAILs. **Unaffected.** |

**DeepSeek-v4-flash-0731 (3 replicates per family)**

| Family | Defect | Finding |
| --- | --- | --- |
| `p2_triage` | D3 | 3 of 3 cells answered `n/a` on all three spam tickets and lost 0.100 each; all three sat far enough above 0.700 that **0 verdicts change**. Scores are wrong; verdicts are not. |
| `p3_pm` | D2 | 3 of 3 raw PASS; no change under R3. The correction was never applied to this campaign, but nothing turned on it. |
| `p3_business` | D1 | 1 length-attributable FAIL, and it is over the ceiling by `wc -w` too. **Verdict stands.** |
| `p3_doc`, `p3_writing` | D1 | 0 length-attributable FAILs. **Unaffected.** |

Conclusions for prior work, in order of how much they matter:

1. **Every published MMBT `p2_triage` urgency accuracy, for every model ever run, is
   understated by 0.100** (and by a further 0.033 if ticket 029 is counted). Every cell in
   every campaign examined answered as the brief instructed. Any cross-model `p2_triage`
   comparison published to date is a comparison of how far each model's remaining errors
   happened to sit from a threshold that had a constant subtracted from it. Concretely,
   2 of 10 Gemma4 verdicts change.
2. **Published raw `p3_pm` results understate every model that writes "has not" instead of
   "hasn't."** The Gemma4 campaign shipped an overlay so its corrected number is sound, but
   its raw 0/10 should never be quoted standalone, and DeepSeek's `p3_pm` was never
   overlaid at all (it happens not to matter, 3/3 raw PASS). Any other campaign graded with
   this file and no overlay is suspect.
3. **D1 did not bite in the prior campaigns measured here** — 1 length-attributable FAIL
   across both, and it fails under both counters. This is a length-of-output property of
   those models, not evidence that the gate is sound. Any campaign whose deliverables land
   within roughly 10% of a ceiling is exposed, and the Qwen comparison in this PR shows what
   that looks like: 62 counter-dependent verdicts out of 183 graded cells in the three
   affected families.
4. **The families outside these five are not implicated by this document.** `p1_bugfix`,
   `p1_refactor`, `p1_testwrite`, `p2_ci`, `p2_extract`, `p2_hallucination`,
   `p3_market`, and the `75pr` / `board_pres` / `invest_memo` suites use different graders
   that contain none of the three defects. That is a statement about these three defects
   only, not a clean bill of health for those graders.

Recommended repository actions, none of which are in this PR's scope:

- Define the word counter in every length-gated brief, or drop the hard threshold.
- Resolve the `task_triage.md` / `phase2_triage.json` contradiction on tickets 004, 009,
  021 and 029 in one direction, and re-grade.
- Replace the `p3_pm` literal keyword bundles with the semantic patterns the repository
  already wrote and tested, in the grader itself rather than in an overlay.
- Never scope a correction script by a hardcoded cell-name prefix again.

---

## Appendix A — the 71 length-attributable FAIL cells (D1)

Format: `cap / grader-regex count / wc -w count`, listing only the deliverables that
exceed their cap under the grader's regex. A cell is marked **under every cap** when no
deliverable exceeds its cap under `wc -w`; those are the 62 the overlay corrects.

| cell | model | deliverable cap / regex / `wc -w` | `wc -w` verdict |
| --- | --- | --- | --- |
| `p3_business_qwen36-nothink-offspec_v4` | 3.6 | memo 700/719/699 | **under every cap** |
| `p3_business_qwen36-nothink-offspec_v8` | 3.6 | memo 700/731/725 | over |
| `p3_business_qwen36-think-offspec_v7` | 3.6 | memo 700/703/700 | **under every cap** |
| `p3_doc_qwen36-nothink-offspec_v7` | 3.6 | brief 700/713/696 | **under every cap** |
| `p3_doc_qwen36-think-offspec_v1` | 3.6 | brief 700/707/698 | **under every cap** |
| `p3_doc_qwen36-think-offspec_v2` | 3.6 | brief 700/707/698 | **under every cap** |
| `p3_doc_qwen36-think-offspec_v3` | 3.6 | brief 700/707/698 | **under every cap** |
| `p3_doc_qwen36-think-offspec_v4` | 3.6 | brief 700/707/698 | **under every cap** |
| `p3_doc_qwen36-think-offspec_v5` | 3.6 | brief 700/707/698 | **under every cap** |
| `p3_doc_qwen36-think-offspec_v6` | 3.6 | brief 700/707/700 | **under every cap** |
| `p3_doc_qwen36-think-offspec_v7` | 3.6 | brief 700/707/698 | **under every cap** |
| `p3_doc_qwen36-think-offspec_v8` | 3.6 | brief 700/707/698 | **under every cap** |
| `p3_doc_qwen36-think-offspec_v9` | 3.6 | brief 700/709/698 | **under every cap** |
| `p3_writing_qwen36-nothink-card_v2` | 3.6 | ceo_brief 250/253/242; customer_email 350/358/347 | **under every cap** |
| `p3_writing_qwen36-nothink-card_v3` | 3.6 | ceo_brief 250/254/243 | **under every cap** |
| `p3_writing_qwen36-nothink-card_v7` | 3.6 | ceo_brief 250/257/245 | **under every cap** |
| `p3_writing_qwen36-nothink-card_v9` | 3.6 | ceo_brief 250/255/248 | **under every cap** |
| `p3_writing_qwen36-think-card_v2` | 3.6 | customer_email 350/358/346 | **under every cap** |
| `p3_writing_qwen36-think-card_v3` | 3.6 | customer_email 350/358/346 | **under every cap** |
| `p3_writing_qwen36-think-card_v6` | 3.6 | customer_email 350/358/346 | **under every cap** |
| `p3_writing_qwen36-think-offspec_v2` | 3.6 | ceo_brief 250/252/242 | **under every cap** |
| `p3_writing_qwen36-think-offspec_v5` | 3.6 | ceo_brief 250/252/242 | **under every cap** |
| `p3_writing_qwen36-think-offspec_v8` | 3.6 | ceo_brief 250/252/242 | **under every cap** |
| `p3_writing_qwen36-think-offspec_v9` | 3.6 | ceo_brief 250/252/242 | **under every cap** |
| `p3_business_qwen38-27b-udq4xl-nothink_v1` | 3.8 | memo 700/817/753 | over |
| `p3_business_qwen38-27b-udq4xl-think-xhigh_v1` | 3.8 | memo 700/723/694 | **under every cap** |
| `p3_business_qwen38-27b-udq4xl-think-xhigh_v2` | 3.8 | memo 700/742/694 | **under every cap** |
| `p3_business_qwen38-27b-udq4xl-think-xhigh_v3` | 3.8 | memo 700/749/697 | **under every cap** |
| `p3_business_qwen38-nothink-card_v1` | 3.8 | memo 700/860/832 | over |
| `p3_business_qwen38-nothink-card_v2` | 3.8 | memo 700/775/713 | over |
| `p3_business_qwen38-nothink-offspec_v1` | 3.8 | memo 700/738/699 | **under every cap** |
| `p3_business_qwen38-nothink-offspec_v2` | 3.8 | memo 700/742/707 | over |
| `p3_business_qwen38-nothink-offspec_v4` | 3.8 | memo 700/723/697 | **under every cap** |
| `p3_business_qwen38-nothink-offspec_v5` | 3.8 | memo 700/754/698 | **under every cap** |
| `p3_business_qwen38-nothink-offspec_v6` | 3.8 | memo 700/732/699 | **under every cap** |
| `p3_business_qwen38-nothink-offspec_v7` | 3.8 | memo 700/731/695 | **under every cap** |
| `p3_business_qwen38-think-low-card_v1` | 3.8 | memo 700/725/691 | **under every cap** |
| `p3_business_qwen38-think-medium-card_v1` | 3.8 | memo 700/744/698 | **under every cap** |
| `p3_business_qwen38-think-medium-offspec_v2` | 3.8 | memo 700/741/696 | **under every cap** |
| `p3_business_qwen38-think-xhigh-card_v1` | 3.8 | memo 700/725/699 | **under every cap** |
| `p3_business_qwen38-think-xhigh-offspec_v1` | 3.8 | memo 700/724/690 | **under every cap** |
| `p3_business_qwen38q8-nothink-matched_v1` | 3.8 | memo 700/748/714 | over |
| `p3_doc_qwen38-27b-udq4xl-nothink_v1` | 3.8 | brief 700/702/679 | **under every cap** |
| `p3_doc_qwen38-27b-udq4xl-nothink_v2` | 3.8 | brief 700/727/700 | **under every cap** |
| `p3_doc_qwen38-27b-udq4xl-think-xhigh_v1` | 3.8 | brief 700/722/682 | **under every cap** |
| `p3_doc_qwen38-27b-udq4xl-think-xhigh_v2` | 3.8 | brief 700/719/689 | **under every cap** |
| `p3_doc_qwen38-27b-udq4xl-think-xhigh_v3` | 3.8 | brief 700/725/694 | **under every cap** |
| `p3_doc_qwen38-nothink-card_v1` | 3.8 | brief 700/722/694 | **under every cap** |
| `p3_doc_qwen38-nothink-card_v2` | 3.8 | brief 700/722/694 | **under every cap** |
| `p3_doc_qwen38-nothink-card_v3` | 3.8 | brief 700/718/688 | **under every cap** |
| `p3_doc_qwen38-nothink-card_v4` | 3.8 | brief 700/730/699 | **under every cap** |
| `p3_doc_qwen38-nothink-card_v5` | 3.8 | brief 700/733/700 | **under every cap** |
| `p3_doc_qwen38-think-medium-card_v1` | 3.8 | brief 700/701/692 | **under every cap** |
| `p3_doc_qwen38-think-medium-offspec_v1` | 3.8 | brief 700/708/696 | **under every cap** |
| `p3_doc_qwen38-think-medium-offspec_v2` | 3.8 | brief 700/720/713 | over |
| `p3_doc_qwen38-think-xhigh-card_v1` | 3.8 | brief 700/726/697 | **under every cap** |
| `p3_doc_qwen38-think-xhigh-offspec_v1` | 3.8 | brief 700/723/696 | **under every cap** |
| `p3_doc_qwen38q8-nothink-matched_v1` | 3.8 | brief 700/772/757 | over |
| `p3_writing_qwen38-27b-udq4xl-nothink_v1` | 3.8 | ceo_brief 250/255/246; customer_email 350/358/348 | **under every cap** |
| `p3_writing_qwen38-27b-udq4xl-nothink_v3` | 3.8 | ceo_brief 250/308/301; customer_email 350/355/346 | over |
| `p3_writing_qwen38-27b-udq4xl-think-xhigh_v1` | 3.8 | ceo_brief 250/258/246; legal_summary 400/410/394 | **under every cap** |
| `p3_writing_qwen38-27b-udq4xl-think-xhigh_v2` | 3.8 | ceo_brief 250/258/249; customer_email 350/351/345 | **under every cap** |
| `p3_writing_qwen38-27b-udq4xl-think-xhigh_v3` | 3.8 | ceo_brief 250/260/246; legal_summary 400/401/391 | **under every cap** |
| `p3_writing_qwen38-nothink-card_v2` | 3.8 | ceo_brief 250/258/248; customer_email 350/358/348 | **under every cap** |
| `p3_writing_qwen38-nothink-card_v5` | 3.8 | ceo_brief 250/256/249; customer_email 350/360/350 | **under every cap** |
| `p3_writing_qwen38-think-low-card_v1` | 3.8 | ceo_brief 250/252/249; customer_email 350/359/348 | **under every cap** |
| `p3_writing_qwen38-think-medium-card_v1` | 3.8 | ceo_brief 250/264/246 | **under every cap** |
| `p3_writing_qwen38-think-medium-offspec_v1` | 3.8 | ceo_brief 250/260/250 | **under every cap** |
| `p3_writing_qwen38-think-medium-offspec_v2` | 3.8 | ceo_brief 250/259/249 | **under every cap** |
| `p3_writing_qwen38-think-xhigh-card_v1` | 3.8 | ceo_brief 250/251/243; customer_email 350/351/347 | **under every cap** |
| `p3_writing_qwen38-think-xhigh-offspec_v1` | 3.8 | ceo_brief 250/257/249 | **under every cap** |

71 rows: 62 under every cap (corrected), 9 over (verdict stands). The two Q8_0 control
cells (`p3_business_qwen38q8-nothink-matched_v1`, `p3_doc_qwen38q8-nothink-matched_v1`)
are in the 3.8 rows and both stand as over.

---

## Appendix B — reproducing these claims

Every claim above reads only immutable artefacts: `grade.json`, `workspace_final.tar.gz`,
`transcript.jsonl`, the graders, the briefs and the ground truth. Nothing was rewritten.

**D2's natural experiment**, the single fastest check — three commands, no scripts:

```sh
cd mmbt-q36-card
for v in v2 v4 v8; do
  tar -xzOf logs/p3_pm_qwen36-nothink-card_$v/workspace_final.tar.gz ./status_report.md \
    | sed -n 22p
done
for v in v2 v4 v8; do
  python3 -c "import json;g=json.load(open('logs/p3_pm_qwen36-nothink-card_$v/grade.json'));\
print('$v', g['verdict'], g['scores']['risk_recall'], g['details']['risks']['R3'])"
done
```

Expect: v2 and v8 print `Legal has not responded`, `FAIL`, `2/6`, R3 unmatched; v4 prints
`Legal hasn't responded`, `PASS`, `3/6`, R3 matched on `legal hasn't`. Every other score
in the three grades is identical.

**D1's counter divergence**, on any length-attributable FAIL from Appendix A:

```sh
tar -xzOf mmbt-qwen36-compare/logs/p3_doc_qwen36-think-offspec_v1/workspace_final.tar.gz \
  ./brief.md > /tmp/brief.md
python3 -c "import re;t=open('/tmp/brief.md').read();print('regex',len(re.findall(r'\b\w+\b',t)))"
LC_ALL=C.UTF-8 wc -w /tmp/brief.md
```

Expect 707 and 698 against a ceiling of 700.

**D3's contradiction**, one command each:

```sh
sed -n 27p mmbt-q38-card/tooling/tasks/task_triage.md
python3 -c "import json;d=json.load(open('mmbt-q38-card/tooling/graders/ground_truth/phase2_triage.json'));\
print({k:v['urgency'] for k,v in d['tickets'].items() if v['category']=='spam-or-noise'})"
```

Expect the brief to define `n/a` for noise/spam and the ground truth to answer
`{'004': 'low', '009': 'low', '021': 'low'}`.

The per-cell overlay records under `overlay/<repo>/logs/<cell>/grade.corrected.json` carry
the raw `grade.json` sha256, the deliverable sha256, the frozen-dataset verdict, the
defect evidence and both word counts, so any single correction can be checked in isolation
without re-running the pipeline.

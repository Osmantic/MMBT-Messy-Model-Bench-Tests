#!/usr/bin/env python3
"""Grader-defect diagnostics for the MMBT 3.6-vs-3.8 PR.

PROVENANCE NOTE: unlike every other number in results.json, this block is
computed from the raw grade.json files rather than from the frozen CSV. That
is deliberate and allowed -- the frozen CSV carries only the final pass/fail
bit, and diagnosing WHY a cell failed requires the grader's own score fields.
No headline pass rate is computed here. Cell->model identity is taken from the
frozen CSV, never inferred from the directory name.
"""
import csv, glob, json, os, collections

REPOS = ["mmbt-q36-card", "mmbt-qwen36-compare", "mmbt-q38-card",
         "mmbt-qwen38-eaaa8ca", "mmbt-q38-q8"]
CSV_PATH = "/home/michael/mmbt-frozen-dataset-v2.csv"
RESULTS = "/home/michael/pr-staging/results.json"

# cell -> identity, straight from the frozen dataset
IDENT = {}
for r in csv.DictReader(open(CSV_PATH)):
    IDENT[r["cell"]] = r


def grades(family):
    out = []
    for repo in REPOS:
        for gp in glob.glob("/home/michael/%s/logs/%s_*/grade.json" % (repo, family)):
            cell = os.path.basename(os.path.dirname(gp))
            if cell.startswith("_"):
                continue
            ident = IDENT.get(cell)
            if ident is None:
                continue  # not in the frozen set -> not counted
            if ident.get("graded") != "1":
                # Ungraded AS OF THE FREEZE: any grade.json present here was
                # written after the freeze (post-freeze drift, e.g. the Q8_0
                # arm). The frozen CSV is the source of truth, so these cells
                # stay out of the diagnostics exactly as they stay out of the
                # headline numbers. Disclosed in quant_control.post_freeze_drift.
                continue
            try:
                out.append((cell, ident["model"], json.load(open(gp))))
            except Exception:
                pass
    return out


D = {"provenance": "computed from raw grade.json; identity joined from frozen CSV by cell id; "
                   "cells with graded==0 in the frozen CSV are excluded even if a grade.json "
                   "now exists on disk (post-freeze drift)",
     "note": "Diagnostics only. These do NOT alter any pass rate reported elsewhere; the "
             "results tables are strictly as-graded."}

# ---- D3: p2_triage spam-urgency penalty -----------------------------------
SPAM = {"004", "009", "021"}
tri = grades("p2_triage")
d3 = dict(n_cells=len(tri), all_three_spam_na=0, fails=0,
          fail_blocked_by_urgency_only=0, would_flip_to_pass=collections.Counter(),
          verdicts=collections.Counter(), by_model=collections.Counter())
for cell, model, g in tri:
    s = g.get("scores") or {}
    if not s:
        continue
    ue = g.get("errors", {}).get("urgency_errors", [])
    spam_na = sum(1 for e in ue
                  if e["id"] in SPAM and e.get("predicted") == "n/a" and e.get("actual") == "low")
    if spam_na == 3:
        d3["all_three_spam_na"] += 1
    d3["verdicts"][g["verdict"]] += 1
    d3["by_model"][model + ":" + g["verdict"]] += 1
    if g["verdict"] == "FAIL":
        d3["fails"] += 1
        blocked_urg = s["urgency_accuracy"] < 0.70
        blocked_other = s["category_accuracy"] < 0.80 or s["duplicate_recall"] < 0.50
        if blocked_urg and not blocked_other:
            d3["fail_blocked_by_urgency_only"] += 1
        # restore the 3 spam tickets (30 tickets total in the ground truth)
        adj = s["urgency_accuracy"] + spam_na / 30.0
        if adj >= 0.70 and not blocked_other:
            d3["would_flip_to_pass"][model] += 1
d3["would_flip_to_pass"] = dict(d3["would_flip_to_pass"])
d3["verdicts"] = dict(d3["verdicts"])
d3["by_model"] = dict(d3["by_model"])
d3["correction_favours"] = "3.6"
D["D3_p2_triage"] = d3

# ---- D1: phase-3 word gate ------------------------------------------------
d1 = {}
# p3_business: single memo, explicit within-limit flag
bus = collections.defaultdict(lambda: collections.Counter())
for cell, model, g in grades("p3_business"):
    s = g.get("scores") or {}
    bus[model]["n"] += 1
    bus[model][g["verdict"]] += 1
    if s.get("memo_within_word_limit") is False:
        bus[model]["over_limit"] += 1
        if g["verdict"] == "FAIL":
            bus[model]["fail_with_over_limit"] += 1
    if g["verdict"] == "FAIL" and s.get("stance_pushback") is False:
        bus[model]["fail_with_stance_miss"] += 1
d1["p3_business"] = {m: dict(v) for m, v in bus.items()}

doc = collections.defaultdict(lambda: collections.Counter())
overs = collections.defaultdict(list)
for cell, model, g in grades("p3_doc"):
    s = g.get("scores") or {}
    doc[model]["n"] += 1
    doc[model][g["verdict"]] += 1
    if s.get("within_word_limit") is False:
        doc[model]["over_limit"] += 1
        overs[model].append(s.get("word_count"))
d1["p3_doc"] = {m: dict(v) for m, v in doc.items()}
d1["p3_doc_overshoot_wordcounts"] = {m: sorted(v) for m, v in overs.items()}
d1["p3_doc_limit"] = 700

wri = collections.defaultdict(lambda: collections.Counter())
for cell, model, g in grades("p3_writing"):
    wri[model]["n"] += 1
    wri[model][g["verdict"]] += 1
    pa = g.get("per_audience") or {}
    only_len = None
    for _, sub in pa.items():
        if sub.get("verdict") == "FAIL":
            if sub.get("within_word_limit") is False and \
               sub.get("required_content_pass") and sub.get("prohibited_content_pass"):
                only_len = True if only_len is None else only_len
            else:
                only_len = False
    if g.get("verdict") == "FAIL" and only_len:
        wri[model]["fail_length_only"] += 1
d1["p3_writing"] = {m: dict(v) for m, v in wri.items()}
d1["correction_favours"] = "3.8"
D["D1_word_gate"] = d1

# ---- D2: p3_pm risk-keyword literalism ------------------------------------
pm = collections.defaultdict(lambda: collections.Counter())
risk_short = collections.defaultdict(list)
for cell, model, g in grades("p3_pm"):
    s = g.get("scores") or {}
    pm[model]["n"] += 1
    pm[model][g["verdict"]] += 1
    rr = s.get("risk_recall")
    if isinstance(rr, str) and "/" in rr:
        got, tot = rr.split("/")
        got, tot = int(got), int(tot)
        risk_short[model].append(got)
        if g["verdict"] == "FAIL" and got < 3:
            pm[model]["fail_with_risk_recall_below_min"] += 1
    if s.get("word_count") is not None and s["word_count"] > 700:
        pm[model]["over_word_limit"] += 1
d2 = {m: dict(v) for m, v in pm.items()}
d2["risk_recall_distribution"] = {m: dict(collections.Counter(v)) for m, v in risk_short.items()}
d2["min_risks_threshold"] = 3
d2["correction_favours"] = "3.6"
D["D2_p3_pm"] = d2

R = json.load(open(RESULTS))
R["defect_diagnostics"] = D
json.dump(R, open(RESULTS, "w"), indent=2)
print(json.dumps(D, indent=2))

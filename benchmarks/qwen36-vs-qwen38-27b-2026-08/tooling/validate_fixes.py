#!/usr/bin/env python3
"""Post-edit validation for the claims + limitations component (freeze #2).

Every expectation below is pinned to the freeze-2 dataset
(/home/michael/mmbt-frozen-dataset-v2.csv, 802 cells, 2026-08-16T14:23:09Z)
and the freeze-2 overlay digest. The freeze-1 constants this file used to
carry are now in the stale list."""
import csv, json, glob, sys, collections

CLAIMS = "/home/michael/pr-staging/claims-additions.yaml"
LIMITS = "/home/michael/pr-staging/known-limitations-additions.md"
failures = []

def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name + ((" | " + detail) if detail else ""))
    if not cond:
        failures.append(name)

# ---- 1. PyYAML parse ----
import yaml
with open(CLAIMS, encoding="utf-8") as f:
    doc = yaml.safe_load(f)
check("yaml parses", isinstance(doc, dict))
check("claims count", len(doc.get("claims", [])) == 7, str(len(doc.get("claims", []))))
check("retracted count", len(doc.get("retracted", [])) == 5, str(len(doc.get("retracted", []))))
ids = [c["id"] for c in doc["claims"]] + [r["id"] for r in doc["retracted"]]
check("ids unique", len(ids) == len(set(ids)))

cl = {c["id"]: c for c in doc["claims"]}
rt = {r["id"]: r for r in doc["retracted"]}
claims_txt = open(CLAIMS, encoding="utf-8").read()
limits_txt = open(LIMITS, encoding="utf-8").read()

# ---- 2. stale numbers gone (early drafts AND superseded freeze-1 figures) ----
stale = ["91/114", "91/105", "90/107", "79.8%", "86.7%", "84.1%", "108/120",
         "44/61", "72.1%", "~18pp", "59/59", "19 to 22", "3.8 9-12",
         "12/12 exact agreement", "sign of the\n      difference flips",
         # freeze-1 figures superseded by freeze #2
         "39/46", "34/41", "47/61", "40/54", "36/46", "36/43", "104/108",
         "108/110", "46/72", "61/81", "58/58", "16 to 37", "18 to 21",
         "34/37", "55 of the 58", "148 of 148", "86 of 89",
         "138 measurements", "35 gate-invalidated", "64 cells fail",
         "57 of those 64", "EXISTENCE ONLY", "3/11", "11-cell",
         "26 of 746", "46 labelled", "3.8 5-11", "0/11 on p1_bugfix"]
# NOT in the stale list: "17/21 against 4/37" is the historical formerly_claimed
# quote inside the p3_pm retraction (retractions preserve the original wording),
# and "n=11" is the current effort-ladder xhigh subset size.
for s in stale:
    check("stale gone: %r" % s, s not in claims_txt)
for s in ["5-12", "3.8 5-11", "(15/291", "10/265", "(0/64", "of 683",
          "all 273", "59 cells", "110 vs 72", "120 vs 81", "121 vs 72",
          "of those 11", "11-cell"]:
    check("stale gone in limits: %r" % s, s not in limits_txt)

# ---- 3. recompute ground truth from frozen CSV + shipped overlay ----
rows = list(csv.DictReader(open("/home/michael/mmbt-frozen-dataset-v2.csv")))
frozen = {r["cell"]: r for r in rows}
graded = [r for r in rows if r["graded"] == "1"]
check("frozen cells 802", len(rows) == 802, str(len(rows)))
check("frozen graded 733", len(graded) == 733, str(len(graded)))
ov = {}
for p in glob.glob("/home/michael/pr-staging/overlay/*/logs/*/grade.corrected.json"):
    j = json.load(open(p))
    ov[j["cell"]] = j
man = json.load(open("/home/michael/pr-staging/overlay/manifest.json"))
print("overlay digest now:", man["overlay_digest"])
check("overlay digest unchanged since analysis",
      man["overlay_digest"] == "e332cd2c78ad94fe264aed7d31e6c64f5273cd9598f889dc1a8fac539e971351")
check("overlay stamped with freeze #2",
      man.get("frozen_dataset_stamp") == "2026-08-16T14:23:09Z"
      and man.get("frozen_dataset", "").endswith("-v2.csv"))
check("post-freeze ledger empty (static corpus)",
      len(man.get("post_freeze_divergence", [1])) == 0)

def corr(r):  # treatment A: D1 gate-invalidated counted as non-failure
    j = ov.get(r["cell"])
    if j is None:
        return r["passed"] == "1"
    if "corrected_verdict" in j:
        return j["corrected_verdict"] == "PASS"
    return bool(j.get("gate_invalidated"))
def d1cell(r):
    j = ov.get(r["cell"])
    return bool(j and "D1" in j["defects_applied"])

def rates(model, mode, regime, excl_triage=False):
    rs = [r for r in graded if r["model"] == model and r["quant"] == "UD-Q4_K_XL"
          and r["mode"] == mode and r["regime"] == regime]
    if excl_triage:
        rs = [r for r in rs if r["family"] != "p2_triage"]
    a = (sum(1 for r in rs if corr(r)), len(rs))
    rb = [r for r in rs if not d1cell(r)]
    b = (sum(1 for r in rb if corr(r)), len(rb))
    raw = (sum(1 for r in rs if r["passed"] == "1"), len(rs))
    return raw, a, b

exp = {
    ("3.6", "no-think", "T0.3/p0.8/pp0", False): ((81, 114), (98, 114), (96, 112)),
    ("3.8", "no-think", "T0.3/p0.8/pp0", False): ((51, 65), (56, 65), (51, 60)),
    ("3.6", "no-think", "T0.3/p0.8/pp0", True):  ((81, 105), (89, 105), (87, 103)),
    ("3.8", "no-think", "T0.3/p0.8/pp0", True):  ((44, 58), (49, 58), (44, 53)),
    ("3.6", "think", "T0.3/p0.8/pp0", False):    ((67, 107), (99, 107), (85, 93)),
    ("3.8", "think", "T0.3/p0.8/pp0", False):    ((33, 48), (43, 48), (36, 41)),
    ("3.6", "think", "T0.3/p0.8/pp0", True):     ((67, 98), (90, 98), (76, 84)),
    ("3.8", "think", "T0.3/p0.8/pp0", True):     ((29, 44), (39, 44), (32, 37)),
    ("3.6", "no-think", "T1/p0.95/pp0", False):  ((95, 120), (110, 120), (106, 116)),
    ("3.8", "no-think", "T0.7/p0.8/pp1.5", False): ((48, 79), (61, 79), (51, 69)),
    ("3.6", "think", "T1/p0.95/pp0", False):     ((105, 120), (116, 120), (113, 117)),
    ("3.8", "think", "T1/p0.95/pp0", False):     ((54, 72), (72, 72), (55, 55)),
}
for (m, mode, reg, ex), want in exp.items():
    got = rates(m, mode, reg, ex)
    check("rates %s %s %s excl=%s" % (m, mode, reg, ex), got == want, str(got))

# numbers present in claim text
eq = cl["bench.qwen38-vs-qwen36.equivalent-conditional-on-delivery-matched-sampler"]
for frag in ["98/114 (86.0%)", "56/65 (86.2%)", "89/105 (84.8%)", "49/58 (84.5%)",
             "99/107 (92.5%)", "43/48 (89.6%)", "90/98 (91.8%)", "39/44 (88.6%)",
             "62 D1 gate-invalidated"]:
    check("equivalence text has %s" % frag, frag in eq["text"])
check("equivalence: no sign-flip framing", "sign" in eq["text"] and "flips" not in eq["text"])
cavs = "\n".join(eq["caveats"])
for frag in ["110/120 (91.7%)", "61/79 (77.2%)", "~15pp", "106/116", "51/69",
             "96/112 (85.7%)", "51/60 (85.0%)", "85/93 (91.4%)", "36/41 (87.8%)",
             "81/114", "51/65", "62 verdicts counter-dependent"]:
    check("equivalence caveats have %s" % frag, frag in cavs)

# ---- 4. D1 claim vs census/overlay ----
d1 = [r for r in graded if d1cell(r)]
check("D1 total 62", len(d1) == 62, str(len(d1)))
byfam = collections.Counter(r["family"] for r in d1)
bymod = collections.Counter(r["model"] for r in d1)
check("D1 by family 24/23/15",
      byfam == collections.Counter({"p3_doc": 24, "p3_writing": 23, "p3_business": 15}), str(byfam))
check("D1 by model 23/39", bymod == collections.Counter({"3.6": 23, "3.8": 39}), str(bymod))
wg = cl["bench.grader.word-gate-counter-disagreement"]
for frag in ["71 cells fail", "p3_doc 26, p3_writing 24, p3_business 21", "3.8 47 and 3.6 24",
             "62 of those 71", "p3_doc 24, p3_writing 23, p3_business 15", "3.8 39 and 3.6 23",
             "gate-invalidated", "152 of 152", "93 of 95"]:
    check("word-gate text has %r" % frag[:40], frag in wg["text"])
wcavs = "\n".join(wg["caveats"])
for frag in ["all 147 measurements", "LC_ALL=C.UTF-8",
             "39 gate-invalidated single-deliverable cells (24 p3_doc, 15 p3_business)",
             "1 to 54 words"]:
    check("word-gate caveats have %r" % frag[:40], frag in wcavs)

# ---- 5. triage retraction vs frozen ----
tri = [r for r in graded if r["family"] == "p2_triage"]
t36 = [r for r in tri if r["model"] == "3.6"]; t38 = [r for r in tri if r["model"] == "3.8"]
check("triage frozen 64", len(tri) == 64, str(len(tri)))
check("triage 3.6 17->38", (sum(1 for r in t36 if r["passed"] == "1"),
                            sum(1 for r in t36 if corr(r)), len(t36)) == (17, 38, 38))
check("triage 3.8 23->26", (sum(1 for r in t38 if r["passed"] == "1"),
                            sum(1 for r in t38 if corr(r)), len(t38)) == (23, 26, 26))
check("triage 3.8 includes 1 Q8 cell",
      sum(1 for r in t38 if r["quant"] == "Q8_0") == 1)
check("triage flips 24", sum(1 for r in tri if corr(r) and r["passed"] != "1") == 24)
accs = {ov[r["cell"]]["evidence"]["D3"]["category_accuracy"] for r in tri}
check("triage accuracy 0.867 all 64", accs == {0.867}, str(accs))
tr = rt["bench.p2_triage.family-result"]
for frag in ["64/64", "All 64 frozen graded", "17 to 38", "23 to 26", "24 verdict flips",
             "admitted as graded at freeze #2"]:
    check("triage retraction has %r" % frag[:40], frag in tr["text"] + tr["reason"])

# ---- 6. p3_pm retraction vs overlay ----
pm = [r for r in graded if r["family"] == "p3_pm"]
p36 = [r for r in pm if r["model"] == "3.6"]; p38 = [r for r in pm if r["model"] == "3.8"]
check("p3_pm 3.6 4->35/38", (sum(1 for r in p36 if r["passed"] == "1"),
                             sum(1 for r in p36 if corr(r)), len(p36)) == (4, 35, 38))
check("p3_pm 3.8 21->26/26", (sum(1 for r in p38 if r["passed"] == "1"),
                              sum(1 for r in p38 if corr(r)), len(p38)) == (21, 26, 26))
d2 = [r for r in graded if ov.get(r["cell"]) and "D2" in ov[r["cell"]]["defects_applied"]]
check("D2 touched 39", len(d2) == 39, str(len(d2)))
check("D2 flips 36", sum(1 for r in d2 if corr(r) != (r["passed"] == "1")) == 36)
pmr = rt["bench.p3_pm.qwen38-outscores-qwen36"]
for frag in ["61 of the 64 graded p3_pm cells pass", "35/38", "26/26",
             "credits R3 on 39 cells", "flips 36 verdicts", "25/64", "4/38", "21/26"]:
    check("p3_pm retraction has %r" % frag[:40], frag in pmr["text"] + pmr["reason"])

# ---- 7. win counts for nine-three retraction ----
def wins(mode, use_corr):
    out = {"3.6": 0, "3.8": 0, "tie": 0, "skip": 0}
    for fam in sorted({r["family"] for r in graded}):
        res = {}
        for m in ("3.6", "3.8"):
            rs = [r for r in graded if r["model"] == m and r["quant"] == "UD-Q4_K_XL"
                  and r["mode"] == mode and r["regime"] == "T0.3/p0.8/pp0" and r["family"] == fam]
            res[m] = None if not rs else (sum(1 for r in rs if (corr(r) if use_corr else r["passed"] == "1")) / len(rs))
        if res["3.6"] is None or res["3.8"] is None:
            out["skip"] += 1
            continue
        out["3.6" if res["3.6"] > res["3.8"] else ("3.8" if res["3.8"] > res["3.6"] else "tie")] += 1
    return out
check("no-think raw 4/5/3", wins("no-think", False) == {"3.6": 4, "3.8": 5, "tie": 3, "skip": 0},
      str(wins("no-think", False)))
check("no-think corr 4/3/5", wins("no-think", True) == {"3.6": 4, "3.8": 3, "tie": 5, "skip": 0},
      str(wins("no-think", True)))
check("think raw 4/5/3", wins("think", False) == {"3.6": 4, "3.8": 5, "tie": 3, "skip": 0},
      str(wins("think", False)))
check("think corr 4/2/6", wins("think", True) == {"3.6": 4, "3.8": 2, "tie": 6, "skip": 0},
      str(wins("think", True)))
nn = rt["bench.family-paired.nine-three"]
for frag in ["4 (3.6) / 5 (3.8) / 3 tied", "4 / 3 / 5", "4 / 5 / 3 raw", "4 / 2 / 6",
             "all twelve computable at freeze #2"]:
    check("nine-three has %r" % frag, frag in nn["reason"])

# ---- 8. replicate depth + Q8 rate claim + cross-file agreement ----
cnt = collections.Counter()
for r in rows:
    if r["quant"] == "UD-Q4_K_XL":
        cnt[(r["model"], r["mode"], r["regime"], r["family"])] += 1
def rng(model, mode, reg):
    v = [n for (m, mo, rg, f), n in cnt.items() if (m, mo, rg) == (model, mode, reg)]
    return min(v), max(v)
check("3.8 nothink matched depth 7-13", rng("3.8", "no-think", "T0.3/p0.8/pp0") == (7, 13))
check("claims says 3.8 7-13", "3.8 7-13" in claims_txt)
check("limits says 7-13", "Qwen3.8 at the same sampler 7-13" in limits_txt)
check("both say 9-19", "9-19" in claims_txt and "9-19" in limits_txt)
check("both say 4-6 think", "3.8 4-6" in claims_txt and "4-6" in limits_txt)

# Q8 arm: rate-claim ground truth
q8 = [r for r in rows if r["quant"] == "Q8_0"]
q8g = [r for r in q8 if r["graded"] == "1"]
check("q8 19 cells / 12 families", (len(q8), len({r["family"] for r in q8})) == (19, 12))
check("q8 loop 6/19", sum(1 for r in q8 if r["looped_freq30"] == "1") == 6)
check("q8 graded 8 = 5 PASS + 3 FAIL",
      (len(q8g), sum(1 for r in q8g if r["passed"] == "1")) == (8, 5))
q8c = cl["bench.qwen38.q8-reproduces-nothink-loop"]
for frag in ["6 of 19", "31.6%", "[15.4%, 54.0%]", "110, 109, 81, 80 and 71",
             "provisional RATE claim", "Fisher p = 1.0"]:
    check("q8 claim text has %r" % frag, frag in q8c["text"])
q8cavs = "\n".join(q8c["caveats"])
for frag in ["5 PASS, 3 FAIL", "[30.6%, 86.3%]", "p3_doc_qwen38q8-nothink-matched_v2",
             "139 iterations", "~228k", "UNSCORED", "no matched Qwen3.6 Q8_0 arm"]:
    check("q8 claim caveats have %r" % frag, frag in q8cavs)

# quarantined rewrite-loop cell must NOT be a frozen row
check("quarantined q8 cell not in CSV",
      "p3_doc_qwen38q8-nothink-matched_v2" not in frozen)

# shared constants across both files
for frag in ["802 cells", "2026-08-16T14:23:09Z"]:
    check("both files: %r" % frag, frag in claims_txt and frag in limits_txt)
for a, b in [("5 PASS, 3 FAIL", "5 PASS, 3 FAIL"), ("110, 109, 81, 80", "110, 109, 81, 80")]:
    check("q8 grades/runs note both files", a in claims_txt and b in limits_txt)

print()
print("FAILURES:", len(failures))
for f in failures:
    print("  -", f)
sys.exit(1 if failures else 0)

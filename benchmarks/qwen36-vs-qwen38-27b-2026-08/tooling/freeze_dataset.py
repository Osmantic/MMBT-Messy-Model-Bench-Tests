#!/usr/bin/env python3
"""Freeze the Qwen3.6-vs-Qwen3.8 corpus into ONE canonical per-cell dataset.

Every number in the PR must derive from this file and nothing else. Three of four all-cells
figures quoted during the investigation drifted 4-9pp because they were computed against a live
corpus at different moments; a frozen dataset makes that class of error impossible.

The repo gitignores /logs/ ("raw per-run logs and agent workspaces are not published") and the
workspace tarballs alone are 1.5 GB, so the publishable artifact is this derived table.

MODEL AND SAMPLER IDENTITY COME FROM receipt.json, NEVER FROM THE DIRECTORY NAME.
An arm named "...-offspec" was found to actually carry the vendor-card sampler, so filename
inference is unsafe. "nothink" is resolved from enable_thinking, not by substring matching
(the string "nothink" contains "think").

Columns:
  cell, repo, family, arm, replicate, model, quant, mode, effort, regime,
  temperature, top_p, top_k, presence_penalty, seed,
  verdict, graded, terminal, looped_freq30, looped_run30, max_freq, max_run,
  n_tools, distinct_ratio, completion_tokens, elapsed_s, label_primary,
  container_death_signature, transcript_mtime
"""
import csv
import collections
import glob
import json
import os
import re
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "/home/michael/mmbt-frozen-dataset.csv"
REPOS = [
    "/home/michael/mmbt-q38-card",
    "/home/michael/mmbt-qwen38-eaaa8ca",
    "/home/michael/mmbt-q36-card",
    "/home/michael/mmbt-qwen36-compare",
    "/home/michael/mmbt-q38-q8",
]
PASSING = ("PASS", "STRUCTURAL_PASS")
NAME = re.compile(r"^(p[123]_[a-z]+)_(.+)_v(\d+)$")

rows = []
skipped = collections.Counter()

for repo in REPOS:
    for d in sorted(glob.glob(os.path.join(repo, "logs", "*"))):
        base = os.path.basename(d)
        if not os.path.isdir(d) or base.startswith("_"):
            skipped["quarantined_or_notdir"] += 1
            continue
        m = NAME.match(base)
        if not m:
            skipped["unparseable_name"] += 1
            continue
        tpath = os.path.join(d, "transcript.jsonl")
        rpath = os.path.join(d, "receipt.json")
        if not os.path.exists(tpath):
            skipped["no_transcript"] += 1
            continue

        # --- identity from the receipt, never the filename ---
        model = quant = ""
        temp = top_p = top_k = pp = seed = ""
        thinking = None
        effort = ""
        if os.path.exists(rpath):
            try:
                rec = json.load(open(rpath))
            except Exception:
                rec = {}
            served = ((rec.get("vllm") or {}).get("served_model_name")
                      or (rec.get("serving") or {}).get("served_model_name") or "")
            model = served
            dflt = rec.get("inference_request_defaults") or {}
            temp = dflt.get("temperature", "")
            top_p = dflt.get("top_p", "")
            top_k = dflt.get("top_k", "")
            pp = dflt.get("presence_penalty", "")
            seed = dflt.get("seed", "")
            thinking = dflt.get("enable_thinking", None)
            effort = dflt.get("reasoning_effort") or ""
        if not model:
            skipped["no_model_in_receipt"] += 1

        low = model.lower()
        family_model = "3.8" if "3.8" in low or "3-8" in low else ("3.6" if "3.6" in low or "3-6" in low else "?")
        if "q8_0" in low or "q8-0" in low:
            quant = "Q8_0"
        elif "q4_k_xl" in low or "q4-k-xl" in low:
            quant = "UD-Q4_K_XL"
        else:
            quant = "?"

        mode = "no-think" if thinking is False else ("think" if thinking is True else "?")

        # Sampler point recorded VERBATIM rather than bucketed. An earlier binary
        # matched/vendor split was misleading: every Qwen3.8 THINKING arm runs at
        # T1.0/p0.95/pp0.0, which is Qwen3.6s vendor point, NOT Qwen3.8s
        # (T0.7/p0.8/pp1.5). No Qwen3.8 thinking run at Qwen3.8s own vendor sampler
        # exists in this corpus. Bucketing hid that; the verbatim triple exposes it.
        def _f(x):
            try:
                return float(x)
            except Exception:
                return None
        tf, pf, ppf = _f(temp), _f(top_p), _f(pp)
        if tf is None:
            regime = "?"
        else:
            regime = "T%g/p%g/pp%g" % (tf, pf if pf is not None else -1,
                                       ppf if ppf is not None else -1)

        # --- outcomes ---
        verdict = ""
        gpath = os.path.join(d, "grade.json")
        if os.path.exists(gpath):
            try:
                verdict = json.load(open(gpath)).get("verdict") or ""
            except Exception:
                pass
        label_primary = ""
        lpath = os.path.join(d, "label.json")
        if os.path.exists(lpath):
            try:
                label_primary = json.load(open(lpath)).get("primary") or ""
            except Exception:
                label_primary = "unparseable"
        tok = wall = ""
        spath = os.path.join(d, "summary.json")
        has_summary = os.path.exists(spath)
        if has_summary:
            try:
                sj = json.load(open(spath))
                tok = sj.get("total_completion_tokens", "")
                wall = sj.get("elapsed_s", "")
            except Exception:
                pass

        try:
            recs = [json.loads(l) for l in open(tpath) if l.strip()]
        except Exception:
            skipped["unreadable_transcript"] += 1
            continue
        tools = [r for r in recs if r.get("type") == "tool"]
        n_tools = len(tools)
        max_freq = max_run = 0
        distinct_ratio = ""
        dead_frac = 0.0
        if n_tools:
            blobs = [json.dumps(r.get("args"), sort_keys=True) for r in tools]
            max_freq = max(collections.Counter(blobs).values())
            cur = mx = 1
            for i in range(1, len(blobs)):
                cur = cur + 1 if blobs[i] == blobs[i - 1] else 1
                mx = max(mx, cur)
            max_run = mx if len(blobs) > 1 else 1
            distinct_ratio = round(len(set(blobs)) / n_tools, 4)
            dead = sum(1 for r in tools
                       if (r.get("wall_s") or 1) <= 0.05 and 130 <= (r.get("result_len") or 0) <= 200)
            dead_frac = dead / n_tools

        rows.append(dict(
            cell=base, repo=os.path.basename(repo), family=m.group(1), arm=m.group(2),
            replicate=int(m.group(3)), model=family_model, quant=quant, mode=mode,
            effort=effort, regime=regime, temperature=temp, top_p=top_p, top_k=top_k,
            presence_penalty=pp, seed=seed,
            verdict=verdict, graded=int(bool(verdict)),
            terminal=int(has_summary or bool(label_primary)),
            passed=int(verdict in PASSING),
            looped_freq30=int(n_tools >= 5 and max_freq >= 30),
            looped_run30=int(n_tools >= 5 and max_run >= 30),
            max_freq=max_freq, max_run=max_run, n_tools=n_tools,
            distinct_ratio=distinct_ratio,
            completion_tokens=tok, elapsed_s=wall, label_primary=label_primary,
            container_death_signature=int(n_tools >= 5 and dead_frac > 0.40),
            transcript_mtime=int(os.path.getmtime(tpath)),
        ))

cols = ["cell", "repo", "family", "arm", "replicate", "model", "quant", "mode", "effort",
        "regime", "temperature", "top_p", "top_k", "presence_penalty", "seed",
        "verdict", "graded", "passed", "terminal", "looped_freq30", "looped_run30",
        "max_freq", "max_run", "n_tools", "distinct_ratio", "completion_tokens",
        "elapsed_s", "label_primary", "container_death_signature", "transcript_mtime"]

rows.sort(key=lambda r: (r["model"], r["mode"], r["regime"], r["family"], r["replicate"]))
with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for r in rows:
        w.writerow(r)

print("wrote %s  (%d cells)" % (OUT, len(rows)))
print("skipped:", dict(skipped))
print()
c = collections.Counter((r["model"], r["quant"], r["mode"], r["regime"]) for r in rows)
print("%-6s%-14s%-10s%-16s%7s" % ("model", "quant", "mode", "regime", "cells"))
for k in sorted(c):
    print("%-6s%-14s%-10s%-16s%7d" % (k[0], k[1], k[2], k[3], c[k]))
print()
print("container-death-signature cells outside quarantine: %d"
      % sum(r["container_death_signature"] for r in rows))
print("cells with unknown model identity: %d" % sum(1 for r in rows if r["model"] == "?"))
print("cells with unknown mode: %d" % sum(1 for r in rows if r["mode"] == "?"))

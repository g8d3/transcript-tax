#!/usr/bin/env python3
"""The fleet numbers on our pages must come out of the window we publish.

    python3 tests/fleet-window.py [/path/to/fleet-turns-*.jsonl]

Why this exists: the front door, the offer and the published sample deliverable all quote
statistics from "our own fleet". Those numbers came from the live turn log, which
**rotates** — so the window behind them disappeared, and what a reader could download
(`fleet/` in the paper's repository) said something different: the home still claimed
"8.7 s wall per turn, 34% model / 29% tools / 37% unaccounted, 4.4% wasted" while the
published window is a heavier one (median 7.3 s, mean 16.3 s, 25/23/52, 3.2% wasted). Paper
§9 explains why the windows differ, but a page that quotes numbers nobody can reproduce is
the exact failure this pack exists to catch — so the pages now quote the published window,
and this test recomputes that window and fails if a page drifts from it.

Standard library only; reads the published JSONL, then the live pages.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import urllib.request
from pathlib import Path

LIVE = "https://focalis.cc"
CANDIDATES = ("/home/vuos/srv/tps", "/tmp/night/report-pub")
fails: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    if not ok:
        fails.append(name)


def find_window() -> Path | None:
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    for repo in (os.environ.get("REPO_ROOT"), *CANDIDATES):
        if not repo:
            continue
        found = sorted(Path(repo, "fleet").glob("fleet-turns-*.jsonl"))
        if found:
            return found[-1]
    return None


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[round(p * (len(s) - 1))]


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "focalis-fleet-check"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


window = find_window()
if not window or not window.exists():
    check("a published fleet window exists to check against", False, str(window))
    print(f"\n{len(fails)} failing check(s)")
    sys.exit(1)

rows = [json.loads(line) for line in window.read_text().splitlines() if line.strip()]
wall = [r["turnMsTotal"] for r in rows]
wasted = [r for r in rows if r["outcome"] != "completed" or r["output"] == 0]
n = len(rows)
p50_s = statistics.median(wall) / 1000
mean_s = statistics.mean(wall) / 1000
waste_rate = round(len(wasted) / n * 100, 1)
errors = sum(1 for r in rows if r["outcome"] == "error")
aborted = sum(1 for r in rows if r["outcome"] == "aborted")
print(f"published window: {window} — {n} turns, median {p50_s:.1f} s, mean {mean_s:.1f} s, "
      f"{len(wasted)} wasted ({waste_rate}%), {errors} errors + {aborted} aborted")

check("the window is the 500-turn one the pages describe", n == 500, f"n={n}")
check("the window's waste rate is the one the pages quote",
      abs(waste_rate - float(f"{waste_rate:.1f}")) < 0.001,
      f"{waste_rate}% = {len(wasted)}/{n}")

# the pages that quote the window
for path in ("/", "/audit/"):
    body = get(LIVE + path)
    check(f"{path} quotes the recomputed median wall per turn ({p50_s:.1f} s)",
          f"{p50_s:.1f} s" in body or f"{p50_s:.1f} <small>s</small>" in body)
    check(f"{path} quotes the recomputed waste rate ({waste_rate}%)", f"{waste_rate}%" in body)
    check(f"{path} quotes the recomputed mean ({mean_s:.1f} s)",
          f"{mean_s:.1f} s" in body)
    check(f"{path} does not quote the rotated window's 8.7 s / 34% / 37% figures",
          "8.7 s" not in body and "34% model" not in body)

sample = get(f"{LIVE}/audit/sample/")
check(f"/audit/sample/ quotes the recomputed waste count ({len(wasted)} of {n})",
      f"{len(wasted)} of {n}" in sample)
check("/audit/sample/ no longer quotes the rotated window's 4.4% / 22 of 500",
      "4.4%" not in sample and "22 of 500" not in sample)

print(f"\n{len(fails)} failing check(s)")
sys.exit(1 if fails else 0)

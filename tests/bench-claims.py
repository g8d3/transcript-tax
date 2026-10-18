#!/usr/bin/env python3
"""The headline benchmark range on the pages must come out of bench.csv.

    python3 tests/bench-claims.py [/path/to/bench.csv]

Why: "2.4–3.4 s median no-op turn, every harness tested" is the first number on the front door
and it is the claim the whole product rests on. It is recomputable — the 65 runs are published
in `bench.csv` and `analyze.py` regenerates the paper's tables from it — but nothing checked
that the pages still agree with the CSV, so a re-run of the benchmark could leave the front door
quoting the old range (the same class as the fleet window and the route matrix).

Standard library only; reads bench.csv, then the live pages and the paper.
"""
from __future__ import annotations

import csv
import os
import statistics
import sys
import urllib.request
from pathlib import Path

LIVE = "https://focalis.cc"
CANDIDATES = ("/home/vuos/srv/tps", "/tmp/night/report-pub", "/tmp/night")
fails: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    if not ok:
        fails.append(name)


def find_csv() -> Path | None:
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    for root in (os.environ.get("REPO_ROOT"), *CANDIDATES):
        if root and Path(root, "bench.csv").exists():
            return Path(root, "bench.csv")
    return None


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "focalis-bench-check"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


src = find_csv()
if not src:
    check("bench.csv exists to check against", False)
    print(f"\n{len(fails)} failing check(s)")
    sys.exit(1)

rows = [r for r in csv.DictReader(src.open())]
steady = [r for r in rows
          if not r.get("notes", "").startswith("ingest") and r.get("wall_s", "").strip()
          and r.get("run", "").isdigit() and 1 <= int(r["run"]) <= 10]
cells: dict[tuple[str, str], list[float]] = {}
for r in steady:
    cells.setdefault((r["harness"], r["size"]), []).append(float(r["wall_s"]))
medians = {k: statistics.median(v) for k, v in cells.items()}
lo, hi = min(medians.values()), max(medians.values())
print(f"{src}: {len(rows)} rows, {len(cells)} cells, per-cell medians "
      f"{lo:.2f}–{hi:.2f} s across {len({h for h, _ in cells})} harnesses")

check("the published series has the 65 runs the pages describe", len(rows) == 65, f"{len(rows)} rows")
check("it covers the three harnesses the pages describe",
      len({h for h, _ in cells}) == 3, str(sorted({h for h, _ in cells})))

forms = (f"{lo:.1f}\u2013{hi:.1f}", f"{lo:.1f}-{hi:.1f}", f"{lo:.1f} to {hi:.1f}")
for path in ("/", "/audit/"):
    body = get(LIVE + path)
    check(f"{path} quotes the recomputed no-op range ({forms[0]} s)",
          any(f in body for f in forms), f"looked for {forms}")
    check(f"{path} quotes the run count ({len(rows)} runs)", f"{len(rows)} runs" in body)

report = Path(os.environ.get("REPO_ROOT") or CANDIDATES[0], "REPORT.md")
if report.exists():
    text = report.read_text()
    check("the paper's claim 1 quotes the same range", any(f in text for f in forms),
          f"looked for {forms}")
    # and its six per-cell medians, which is where a wrong figure hides: claim 1 said zero-S
    # "3.06 s" (the mean) while its own table and errata say the median is 3.05 s.
    claim = next((l for l in text.splitlines() if l.startswith("1. **Steady-state floor")), "")
    pairs = (("pi", "S"), ("pi", "L"), ("pirust", "S"), ("pirust", "L"), ("zero", "S"), ("zero", "L"))
    wanted = [f"{medians[p]:.2f}" for p in pairs]
    missing = [w for w in wanted if w not in claim]
    check("claim 1 quotes the six per-cell medians from bench.csv", not missing,
          f"missing {missing} from claim 1")

print(f"\n{len(fails)} failing check(s)")
sys.exit(1 if fails else 0)

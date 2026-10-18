#!/usr/bin/env python3
"""The paper's §10 table must equal the generated route matrix.

    python3 tests/paper-matrix.py

Why this exists: `routes/MATRIX.md` is **generated** from `routes/matrix.json` (the same rows the
public page renders), while the table inside `REPORT.md` §10 is **hand-copied** from it. That is
exactly how the "318 ms vs 1808 ms (5.7x)" claim survived a re-measurement: the generated page was
right and the hand copies were stale. This test compares the two for every route the paper quotes,
and checks the counts its prose states.

Paths: `REPORT_MD` and `MATRIX_MD` env vars, else the repository root next to this file.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _root() -> Path:
    """Where REPORT.md lives: the repo this test sits in, else the live clone of it (the page
    actually served), else the working copy the night workers use."""
    for cand in (os.environ.get("REPO_ROOT"), HERE.parent, "/home/vuos/srv/tps",
                 "/tmp/night/report-pub"):
        if cand and (Path(cand) / "REPORT.md").exists():
            return Path(cand)
    return Path(os.environ.get("REPO_ROOT", HERE.parent))


ROOT = _root()
REPORT_MD = Path(os.environ.get("REPORT_MD", ROOT / "REPORT.md"))
MATRIX_MD = Path(os.environ.get("MATRIX_MD", ROOT / "routes" / "MATRIX.md"))
fails: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    if not ok:
        fails.append(name)


def split(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_separator(cells: list[str]) -> bool:
    return all(set(c) <= set("-: ") for c in cells if c)


def measured_rows(md: str) -> list[list[str]]:
    """Rows of the *measured* table only. MATRIX.md carries three tables: measured (8 columns,
    header ends with `streamed`), unavailable (3 columns, header ends with `why`) and the catalog
    (3 columns). Only the first is what §10's prose counts."""
    out: list[list[str]] = []
    width = 0
    for line in md.splitlines():
        if not line.startswith("|"):
            continue
        cells = split(line)
        if not cells or is_separator(cells):
            continue
        if cells[0] == "anchor":
            if cells[-1] == "streamed":
                width = len(cells)
            else:
                break
            continue
        if width and len(cells) == width:
            out.append(cells)
    return out


def paper_rows(md: str) -> list[list[str]]:
    """The §10 table: header is `base model | route | $/M in | …`, rows are the same width."""
    section = md[md.find("## 10."):] if "## 10." in md else ""
    out: list[list[str]] = []
    header = False
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = split(line)
        if not cells or is_separator(cells):
            continue
        if cells[0] == "base model" and not header:
            header = True
            continue
        if header and len(cells) >= 6:
            out.append(cells)
    return out


def main() -> int:
    if not REPORT_MD.exists():
        check(f"paper found at {REPORT_MD}", False, "set REPORT_MD")
        return 1
    if not MATRIX_MD.exists():
        check(f"matrix found at {MATRIX_MD}", False, "set MATRIX_MD")
        return 1
    report = REPORT_MD.read_text(encoding="utf-8")
    check("the paper has a §10 route section", "## 10." in report)

    matrix = {(c[0], c[1]): c[2] for c in measured_rows(MATRIX_MD.read_text(encoding="utf-8"))}
    paper = {(c[0], c[1]): c[2] for c in paper_rows(report)}
    check("the generated matrix has rows", len(matrix) >= 5, f"{len(matrix)} rows")
    check("the paper quotes route rows", len(paper) >= 5, f"{len(paper)} rows")

    for key, price_in in paper.items():
        if key not in matrix:
            check(f"§10 row {key[0]} / {key[1]} exists in the generated matrix", False)
            continue
        check(f"§10 price matches the generated matrix for {key[0]} / {key[1]}",
              matrix[key] == price_in, f"paper {price_in} vs matrix {matrix[key]}")

    m = re.search(r"Measured across (\d+) base models and (\d+) route/model pairs", report)
    if m:
        anchors = {k[0] for k in matrix}
        check("§10 prose count of base models matches the generated matrix",
              int(m.group(1)) == len(anchors), f"paper {m.group(1)} vs {len(anchors)}")
        check("§10 prose count of route/model pairs matches the generated matrix",
              int(m.group(2)) == len(matrix), f"paper {m.group(2)} vs {len(matrix)}")
    else:
        check("§10 states how many models and pairs it measured", False)

    # the same section also states a probed-route count for the cache probe, which is a second
    # generated artifact: recompute it from cache.json or the sentence drifts when it is re-probed.
    cache_path = MATRIX_MD.parent / "cache.json"
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        readable = []
        for r in cache:
            first, second = r.get("first") or {}, r.get("second") or {}
            if not (first.get("ok") and second.get("ok")):
                continue
            cached, tokens = second.get("cached_tokens"), second.get("in_tokens")
            if cached is None or not tokens:
                continue
            readable.append(cached > 0)
        hits = sum(readable)
        check(f"§10 cache sentence: readable routes match cache.json ({len(readable)} of {len(cache)})",
              f"{len(readable)} of the {len(cache)}" in report,
              f"cache.json says {len(readable)} of {len(cache)}")
        check(f"§10 cache sentence: hit count matches cache.json ({hits} hits, "
              f"{len(readable) - hits} misses)", f"{hits} reported a hit" in report,
              f"cache.json says {hits} hits, {len(readable) - hits} misses")
    else:
        check("cache.json found for the §10 cache sentence", False, str(cache_path))

    # SECCIÓN 10's own summary is republished as `article.html`, the single artifact people
    # share. If the report is edited and the page is not regenerated, the most-shared copy is
    # silently stale — which is how the previous 37% sentence survived. Check the HTML carries
    # the same figures the report does.
    article = ROOT / "article.html"
    if article.exists():
        html = article.read_text(encoding="utf-8")
        if m:
            same_counts = (f"{m.group(1)} base models" in html
                           and f"{m.group(2)} route/model pairs" in html)
            check("article.html carries the same §10 counts as the report", same_counts,
                  "" if same_counts else "regenerate with build_article.py")
        if cache_path.exists():
            check("article.html carries the same cache-probe count as the report",
                  f"{hits} reported a hit" in html,
                  f"report says '{hits} reported a hit' and article.html does not")
    else:
        check("article.html found for the staleness check", False, str(article))

    print(f"\n{len(fails)} failing check(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

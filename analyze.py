#!/usr/bin/env python3
"""Reproduce the tables and figures of "Transcript Tax 2026" from bench.csv.

  python3 analyze.py            # tables + figures (needs matplotlib for figures)
  python3 analyze.py --tables   # tables only, stdlib only

Numbers are computed from the CSV, never copied by hand; if a printed number
disagrees with REPORT.md, the CSV wins and the report is wrong.
"""

from __future__ import annotations

import argparse
import csv
import statistics as st
from collections import defaultdict

CSV = "bench.csv"


def load() -> list[dict]:
    with open(CSV, newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["run"] = int(r["run"])
        r["wall_s"] = float(r["wall_s"])
        for k in ("llm_ms", "total_ms", "unacc_ms", "in_tok", "cache_tok", "out_tok"):
            r[k] = int(r[k]) if r[k] else 0
    return rows


def cell(name: str, size: str) -> str:
    return f"{name}-{size}"


def steady_table(rows: list[dict]) -> None:
    print("\n## Steady state — PONG runs 1..10 (wall seconds)\n")
    print(f"{'cell':<12}{'n':>3}{'median':>9}{'mean':>8}{'sd':>7}{'min':>7}{'max':>7}{'ingest':>9}")
    by = defaultdict(list)
    for r in rows:
        by[cell(r["harness"], r["size"])].append(r)
    for key in sorted(by):
        runs = sorted(by[key], key=lambda r: r["run"])
        ingest = [r["wall_s"] for r in runs if r["run"] == 0]
        pongs = [r["wall_s"] for r in runs if r["run"] > 0]
        print(
            f"{key:<12}{len(pongs):>3}{st.median(pongs):>9.2f}{st.mean(pongs):>8.2f}"
            f"{st.pstdev(pongs):>7.2f}{min(pongs):>7.2f}{max(pongs):>7.2f}"
            f"{(f'{ingest[0]:.2f}' if ingest else '-'):>9}"
        )


def pi_span_table(rows: list[dict]) -> None:
    print("\n## pi cells — measured spans (ms)\n")
    print(f"{'cell':<12}{'n':>3}{'median llm':>12}{'median unacc':>14}{'median wall ms':>16}")
    for key in ("pi-S", "pi-L"):
        runs = [r for r in rows if cell(r["harness"], r["size"]) == key and r["run"] > 0]
        llm = [r["llm_ms"] for r in runs]
        unacc = [r["unacc_ms"] for r in runs]
        wall = [r["wall_s"] * 1000 for r in runs]
        print(f"{key:<12}{len(runs):>3}{st.median(llm):>12.0f}{st.median(unacc):>14.0f}{st.median(wall):>16.0f}")


def zero_l_table(rows: list[dict]) -> None:
    print("\n## zero-L run by run (cache state vs wall)\n")
    print(f"{'run':>4}{'wall_s':>9}{'in_tok':>9}{'cache_tok':>11}{'out_tok':>9}  note")
    for r in sorted((r for r in rows if cell(r["harness"], r["size"]) == "zero-L"), key=lambda r: r["run"]):
        print(f"{r['run']:>4}{r['wall_s']:>9.2f}{r['in_tok']:>9}{r['cache_tok']:>11}{r['out_tok']:>9}  {r['notes'][:40]}")


def ingest_table(rows: list[dict]) -> None:
    print("\n## Ingest (run 0) — did the big read stick?\n")
    print(f"{'cell':<12}{'wall_s':>9}{'in_tok':>9}{'cache_tok':>11}  note")
    for r in sorted((r for r in rows if r["run"] == 0), key=lambda r: (r["harness"], r["size"])):
        print(f"{cell(r['harness'], r['size']):<12}{r['wall_s']:>9.2f}{r['in_tok']:>9}{r['cache_tok']:>11}  {r['notes'][:44]}")


def figures(rows: list[dict]) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(matplotlib not installed — skipping figures)")
        return

    by = defaultdict(list)
    for r in rows:
        by[cell(r["harness"], r["size"])].append(r)
    keys = sorted(by)

    # fig1: steady-state wall per cell
    fig, ax = plt.subplots(figsize=(8, 4))
    data = [[r["wall_s"] for r in by[k] if r["run"] > 0] for k in keys]
    ax.boxplot(data, tick_labels=keys, showmeans=True)
    for i, k in enumerate(keys, start=1):
        ax.plot(i, st.median([r["wall_s"] for r in by[k] if r["run"] > 0]), "r_", markersize=22)
    ax.set_ylabel("wall (s)")
    ax.set_title("Steady-state PONG wall per cell (red = median)")
    fig.tight_layout()
    fig.savefig("fig1_steady_wall.png", dpi=140)

    # fig2: zero-L wall vs cached tokens
    zl = sorted((r for r in rows if cell(r["harness"], r["size"]) == "zero-L" and r["run"] > 0), key=lambda r: r["run"])
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.scatter([r["cache_tok"] for r in zl], [r["wall_s"] for r in zl])
    for r in zl:
        ax.annotate(str(r["run"]), (r["cache_tok"], r["wall_s"]), textcoords="offset points", xytext=(4, 3), fontsize=8)
    ax.set_xlabel("cached tokens")
    ax.set_ylabel("wall (s)")
    ax.set_title("zero-L: same ~9.4k input, wall follows cache state")
    fig.tight_layout()
    fig.savefig("fig2_zero_cache.png", dpi=140)

    # fig4: pi unaccounted vs llm
    runs = [r for r in rows if r["harness"] == "pi" and r["size"] == "S" and r["run"] > 0]
    fig, ax = plt.subplots(figsize=(8, 4))
    x = [r["run"] for r in runs]
    ax.bar([i - 0.2 for i in x], [r["llm_ms"] for r in runs], width=0.4, label="llm span", color="#4477aa")
    ax.bar([i + 0.2 for i in x], [r["unacc_ms"] for r in runs], width=0.4, label="unaccounted", color="#888888")
    ax.set_xlabel("run")
    ax.set_ylabel("ms")
    ax.set_title("pi-S: the model span is milliseconds, the rest is not measured")
    ax.legend()
    fig.tight_layout()
    fig.savefig("fig4_pi_unaccounted.png", dpi=140)

    # fig3: prior 8-session size series (hand-entered in the report; kept as a table)
    series = [(30, 1.0), (108, 1.0), (170, 1.5), (228, 1.7), (3200, 5.0), (9000, 5.0)]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.semilogx([s[0] for s in series], [s[1] for s in series], "o-")
    ax.set_xlabel("transcript (KB, log)")
    ax.set_ylabel("overhead (s)")
    ax.set_title("Prior 8-session series: overhead vs transcript size (n=8, single harness)")
    fig.tight_layout()
    fig.savefig("fig3_size_scaling.png", dpi=140)
    print("\nfigures written: fig1..fig4")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", action="store_true", help="tables only, no matplotlib")
    a = ap.parse_args()
    rows = load()
    print(f"{len(rows)} rows from {CSV}")
    steady_table(rows)
    pi_span_table(rows)
    zero_l_table(rows)
    ingest_table(rows)
    if not a.tables:
        figures(rows)


if __name__ == "__main__":
    main()

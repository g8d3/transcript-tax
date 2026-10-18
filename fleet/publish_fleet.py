#!/usr/bin/env python3
"""Publish and re-analyse a window of our own fleet's turn log.

The paper quotes numbers from our live fleet ("500 live turns, one machine: 8.7 s wall per
turn — 34% model, 29% tools, 37% unaccounted"). That log is the one the
`pi-web-tps-monitor` plugin appends to, and it **rotates** (500 rows / 2 MiB per row-bound
cap), so the exact window the paper used no longer exists on disk. This script makes the
claim checkable anyway:

    python3 fleet/publish_fleet.py export  <path/to/tps-turns.jsonl> [out.jsonl]
    python3 fleet/publish_fleet.py analyze <window.jsonl>

`export` copies a window with two deliberate changes: `sessionId` is replaced by an opaque
label (`s1`, `s2`, …) — a session id is a handle the local daemon accepts, so it does not
leave the machine — and the private session label (`sessionName`, the text of the prompt that
opened the session, present in the turn log since 2026-10-18) is removed. Nothing else is
touched. Rows contain no prompt text and no tool
output: timestamp, model, durations, token counts, outcome, tool names and durations.

`analyze` prints the numbers **twice**, because the answer changed when the monitor did:

  * the method the paper used (monitor before v23): the residual is everything not
    attributed to the model span or tool time, which includes the provider roundtrip;
  * the v23+ method: the provider roundtrip (`preResponseMs`) is measured and subtracted
    first, so the residual is what is genuinely unattributed — a few milliseconds.

No dependencies beyond the standard library.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

KEEP_ALL = True  # every field except sessionId is published


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def usable(rows: list[dict]) -> list[dict]:
    """Same core fields the plugin's own validator requires."""
    out = []
    for r in rows:
        if not isinstance(r, dict) or not isinstance(r.get("ts"), str) or not isinstance(r.get("model"), str):
            continue
        if not all(isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool)
                   for k in ("turnMsTotal", "llmDurationMs", "toolMsTotal", "output")):
            continue
        if r.get("outcome") not in ("completed", "aborted", "error"):
            continue
        out.append(r)
    return out


# Fields that must not leave the machine, in BOTH logs.
#  * `sessionName` is the human label of a session (in practice the text of the prompt that opened
#    it) — the same reason the preview builder drops it. The TURN log started carrying it on
#    2026-10-18, which is how this list stopped being message-samples-only: `export` published it
#    once and this comment is the fix.
PRIVATE_FIELDS = ("sessionName",)
# kept as the older name for anything that imported it
HISTORY_DROP = PRIVATE_FIELDS


def export(src: Path, out: Path) -> None:
    rows = load(src)
    labels: dict[str, str] = {}
    clean = []
    dropped = 0
    for r in rows:
        sid = r.get("sessionId") or "?"
        labels.setdefault(sid, f"s{len(labels) + 1}")
        dropped += sum(1 for k in PRIVATE_FIELDS if k in r)
        r = {k: v for k, v in r.items() if k not in PRIVATE_FIELDS}
        r["sessionId"] = labels[sid]
        clean.append(r)
    out.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in clean))
    print(f"wrote {out} — {len(clean)} rows, {len(labels)} session labels, "
          f"{out.stat().st_size / 1024:.0f} KB, sessionId replaced, "
          f"{dropped} private field(s) dropped")


def export_history(src: Path, out: Path) -> None:
    """Publish a window of the message-sample log, so the example deliverables that read it
    (cache report, size curve) can be reproduced from files a reader can download.

    Same discipline as `export`: `sessionId` becomes an opaque label and the private session
    label is dropped; every measured field is copied verbatim.
    """
    rows = load(src)
    labels: dict[str, str] = {}
    clean = []
    dropped = 0
    for r in rows:
        sid = r.get("sessionId") or "?"
        labels.setdefault(sid, f"s{len(labels) + 1}")
        dropped += sum(1 for k in PRIVATE_FIELDS if k in r)
        r = {k: v for k, v in r.items() if k not in PRIVATE_FIELDS}
        r["sessionId"] = labels[sid]
        clean.append(r)
    out.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in clean))
    print(f"wrote {out} — {len(clean)} rows, {len(labels)} session labels, "
          f"{out.stat().st_size / 1024:.0f} KB, sessionId replaced, "
          f"{', '.join(PRIVATE_FIELDS)} dropped ({dropped} row(s))")


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[round(p * (len(s) - 1))] if s else float("nan")


def stats(rows: list[dict], separate_pre: bool) -> dict:
    seg = {"llm": 0.0, "tools": 0.0, "pre": 0.0, "rest": 0.0}
    rest_values, wall_values, pre_values = [], [], []
    no_pre = clamped = wasted = 0
    for r in rows:
        has_pre = isinstance(r.get("preResponseMs"), (int, float))
        pre = r["preResponseMs"] if (separate_pre and has_pre) else 0
        if not has_pre:
            no_pre += 1
        rest = r["turnMsTotal"] - r["llmDurationMs"] - r["toolMsTotal"] - pre
        if rest < 0:
            clamped += 1
            rest = 0
        seg["llm"] += r["llmDurationMs"]; seg["tools"] += r["toolMsTotal"]
        seg["pre"] += pre; seg["rest"] += rest
        rest_values.append(rest); wall_values.append(r["turnMsTotal"])
        if has_pre:
            pre_values.append(r["preResponseMs"])
        if r["outcome"] != "completed" or r["output"] == 0:
            wasted += 1
    wall = sum(wall_values)
    return dict(
        n=len(rows), wall_h=wall / 3.6e6, wall_mean_s=wall / len(rows) / 1000,
        wall_p50_s=statistics.median(wall_values) / 1000, wall_p90_s=pct(wall_values, 0.9) / 1000,
        share_model=seg["llm"] / wall * 100, share_tools=seg["tools"] / wall * 100,
        share_pre=seg["pre"] / wall * 100, share_rest=seg["rest"] / wall * 100,
        rest_p50_ms=statistics.median(rest_values), rest_p90_ms=pct(rest_values, 0.9),
        rest_worst_s=max(rest_values) / 1000 if rest_values else 0,
        pre_p50_ms=statistics.median(pre_values) if pre_values else float("nan"),
        pre_p90_ms=pct(pre_values, 0.9) if pre_values else float("nan"),
        wasted=wasted, wasted_pct=wasted / len(rows) * 100, no_pre=no_pre, clamped=clamped,
    )


def analyze(path: Path) -> None:
    rows = usable(load(path))
    old = stats(rows, separate_pre=False)
    new = stats(rows, separate_pre=True)
    models = {}
    for r in rows:
        models[r["model"]] = models.get(r["model"], 0) + 1
    print(f"window: {path.name} — {old['n']} usable turns, "
          f"{rows[0]['ts'][:16]}Z → {rows[-1]['ts'][:16]}Z")
    print(f"models: " + ", ".join(f"{m} x{n}" for m, n in sorted(models.items(), key=lambda x: -x[1])))
    print(f"wall: {old['wall_h']:.2f} h total, mean {old['wall_mean_s']:.2f} s/turn, "
          f"p50 {old['wall_p50_s']:.2f} s, p90 {old['wall_p90_s']:.2f} s")
    print()
    print("method the paper used (roundtrip inside the residual):")
    print(f"  model {old['share_model']:.0f}% · tools {old['share_tools']:.0f}% · "
          f"residual {old['share_rest']:.0f}%")
    print(f"  residual p50 {old['rest_p50_ms']:.0f} ms, p90 {old['rest_p90_ms']:.0f} ms, "
          f"worst {old['rest_worst_s']:.0f} s")
    print("v23+ method (roundtrip measured first):")
    print(f"  model {new['share_model']:.0f}% · tools {new['share_tools']:.0f}% · "
          f"roundtrip {new['share_pre']:.0f}% · residual {new['share_rest']:.0f}%")
    print(f"  roundtrip p50 {new['pre_p50_ms']:.0f} ms, p90 {new['pre_p90_ms']:.0f} ms")
    print(f"  residual p50 {new['rest_p50_ms']:.0f} ms, p90 {new['rest_p90_ms']:.0f} ms, "
          f"worst {new['rest_worst_s']:.0f} s")
    print()
    print(f"wasted turns: {old['wasted']}/{old['n']} = {old['wasted_pct']:.1f}% "
          f"(failed, aborted or zero output)")
    print(f"rows without the roundtrip field: {old['no_pre']} · "
          f"rows whose segments exceed the turn wall (clamped): {old['clamped']}")
    print()
    print("markdown table for the README:")
    print("| window | turns | wall/turn | model | tools | roundtrip | residual | wasted |")
    print("|---|---|---|---|---|---|---|---|")
    print(f"| {path.name} (paper's method) | {old['n']} | {old['wall_mean_s']:.1f} s | "
          f"{old['share_model']:.0f}% | {old['share_tools']:.0f}% | — | {old['share_rest']:.0f}% | "
          f"{old['wasted_pct']:.1f}% |")
    print(f"| {path.name} (v23+) | {new['n']} | {new['wall_mean_s']:.1f} s | "
          f"{new['share_model']:.0f}% | {new['share_tools']:.0f}% | {new['share_pre']:.0f}% | "
          f"{new['share_rest']:.0f}% | {new['wasted_pct']:.1f}% |")


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__.strip().splitlines()[0] +
                         "\nusage: publish_fleet.py export|export-history|analyze <file> [out]")
    mode, path = sys.argv[1], Path(sys.argv[2])
    if mode == "export":
        export(path, Path(sys.argv[3]) if len(sys.argv) > 3 else path.with_name("fleet-window.jsonl"))
    elif mode == "export-history":
        export_history(path, Path(sys.argv[3]) if len(sys.argv) > 3 else path.with_name("fleet-history.jsonl"))
    elif mode == "analyze":
        analyze(path)
    else:
        raise SystemExit(f"unknown mode {mode!r} (export, export-history or analyze)")


if __name__ == "__main__":
    main()

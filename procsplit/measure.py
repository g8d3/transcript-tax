#!/usr/bin/env python3
"""Measure the per-turn decomposition from OUTSIDE the harness. Reproducible artifact.

    python3 procsplit/measure.py --out procsplit/procsplit-2026-10-18-warm.json
    python3 procsplit/measure.py --cold --reps 3 --out .../cold.json

Why: the harness times the model stream, not the wait. `pi -p --mode json` writes one
NDJSON event per line, so timestamping the arrival of every line from a parent process gives
a decomposition that depends on no hook inside pi:

    process start  -> first NDJSON line          : boot
    turn_start     -> assistant message_start    : provider roundtrip (as the consumer sees it)
    first text     -> message_end                : streaming

That middle term is the one harness logs miss: pi emits `message_start` only after the
provider has answered, so the clock a companion extension starts at that event measures
milliseconds for a network call that took seconds. Raw JSON is written so every number in
the paper's §5.4, the front page and a paid deliverable can be recomputed from a file rather
than trusted.

`--cold` exports `PI_OPENCODE_SYNC_TTL_MS=0`, which forces the model-catalog fetches an
extension does at startup to run again instead of using their 6-hour cache. Boot is the one
segment where that matters (measured: ~0.37 s with the cache, ~0.93 s without), and the diff
is reported, not smoothed over.

Nothing is hardcoded: workdir, reps, model, provider and command all come from flags.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROMPT = "Reply with exactly the word PONG. Call no tools."
SEGMENTS = [
    ("boot_ms", None, "first_line", "process start → first NDJSON line"),
    ("agent_start_to_turn_start_ms", "agent_start", "turn_start", "agent_start → turn_start"),
    ("pre_ms", "turn_start", "assistant_start", "turn_start → assistant message_start"),
    ("assistant_to_first_text_ms", "assistant_start", "first_text", "message_start → first text delta"),
    ("stream_ms", "first_text", "assistant_end", "first text → message_end"),
    ("total_ms", None, "total", "process start → process exit"),
]


def run_one(cli: list[str], cwd: str, env: dict) -> dict:
    t0 = time.monotonic()
    p = subprocess.Popen(cli, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, bufsize=1, env=env)
    marks: dict[str, float] = {}
    assistant_started = False
    deltas = 0
    for line in p.stdout:  # type: ignore[union-attr]
        now = time.monotonic() - t0
        marks.setdefault("first_line", now)
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        t = ev.get("type")
        if t in ("agent_start", "turn_start"):
            marks.setdefault(t, now)
        if t == "message_start" and (ev.get("message") or {}).get("role") == "assistant" \
                and not assistant_started:
            assistant_started = True
            marks["assistant_start"] = now
        elif t == "message_update":
            if ((ev.get("assistantMessageEvent") or {}).get("type")) == "text_delta":
                deltas += 1
                if deltas == 1:
                    marks["first_text"] = now
        elif t == "message_end" and (ev.get("message") or {}).get("role") == "assistant":
            marks.setdefault("assistant_end", now)
    p.wait()
    marks["total"] = time.monotonic() - t0
    return {k: round(v * 1000, 1) for k, v in marks.items()}


def segments(marks: dict) -> dict:
    out = {}
    for name, a, b, _label in SEGMENTS:
        if b in marks and (a is None or a in marks):
            out[name] = round(marks[b] - (0 if a is None else marks[a]), 1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--provider", default="opencode-go")
    ap.add_argument("--model", default="deepseek-v4.1-flash")
    ap.add_argument("--workdir", default=None,
                    help="working directory for the subprocess (kept, so a warm session is a "
                         "real warm session); a fresh temp dir by default")
    ap.add_argument("--cold", action="store_true",
                    help="force the startup catalog fetches (PI_OPENCODE_SYNC_TTL_MS=0)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    workdir = args.workdir or tempfile.mkdtemp(prefix="procsplit-")
    Path(workdir).mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if args.cold:
        env["PI_OPENCODE_SYNC_TTL_MS"] = "0"
    cli = ["pi", "-p", "--provider", args.provider, "--model", args.model, "--mode", "json",
           "-c", PROMPT]

    def tool(*cmd: str) -> str:
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout.strip()
        except Exception:  # noqa: BLE001
            return ""

    reps = []
    for i in range(1, args.reps + 1):
        marks = run_one(cli, workdir, env)
        seg = segments(marks)
        reps.append({"rep": i, "marks_ms": marks, "segments_ms": seg})
        print(f"rep{i}: total {seg.get('total_ms', '?')} ms | boot {seg.get('boot_ms', '?')} | "
              f"pre {seg.get('pre_ms', '?')} | stream {seg.get('stream_ms', '?')}")

    medians = {}
    for name, *_ in SEGMENTS:
        vals = [r["segments_ms"][name] for r in reps if name in r["segments_ms"]]
        if vals:
            medians[name] = {"median": round(statistics.median(vals), 1),
                             "min": min(vals), "max": max(vals), "n": len(vals)}

    doc = {
        "what": "per-turn decomposition measured from outside the harness",
        "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "label": args.label or ("cold cache (catalog fetches forced)"
                                if args.cold else "warm extension cache"),
        "cold": args.cold,
        "command": " ".join(cli),
        "cwd": ("<workdir provided via --workdir, kept between reps so the session is warm>"
                if args.workdir else "<a fresh temp dir per run>"),
        "prompt": PROMPT,
        "env_override": {"PI_OPENCODE_SYNC_TTL_MS": "0"} if args.cold else {},
        "versions": {"pi": tool("pi", "--version"), "node": tool("node", "--version"),
                     "python": sys.version.split()[0], "platform": platform.platform()},
        "reps": reps,
        "medians_ms": medians,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"\nmedians (ms): " + ", ".join(f"{k}={v['median']:g}" for k, v in medians.items()))
    print(f"wrote {out}" + ("" if args.workdir else f" (workdir {workdir} left in place)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

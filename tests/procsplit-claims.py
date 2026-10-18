#!/usr/bin/env python3
"""The published decomposition must equal the raw runs, and the money copy must use it.

    python3 tests/procsplit-claims.py
    python3 tests/procsplit-claims.py --local     (same run; kept for symmetry with the others)

Why this exists: `procsplit/` is the artifact behind the single sentence the pack sells hardest —
"one lever is measured and removable: the boot" — and behind §5.4, the front page's boot figure,
the intake's process-model question and every paid deliverable's boot line. Those had been copied
by hand from a measurement whose raw data was never kept, and the number had already gone stale
once: the 929 ms we published included two model-catalog fetches, which we then cached, so the
same command on the same machine measures 371 ms warm / 940 ms cold.

So this test recomputes the medians of each published raw run and then fails if any page quotes a
different value, in either direction:
  * the paper's §5.4 table must carry the recomputed medians of both runs;
  * the front page and the offer must carry the warm figure (the common case) *and* name the cold
    one, because a lever quoted at 2.5x its measured size is a sale we cannot deliver on;
  * `tools/roi.py`'s default boot must be the warm median, not a number typed from memory;
  * and the 26 vs 65 wall-hours pair must be the arithmetic of that boot over 10 loops x 100
    turns/day, not a second hand copy.

Paths: the repository next to this file, else `REPO_ROOT`, else the live copy over the network —
so a fresh clone of the published repo runs it as-is.
"""
from __future__ import annotations

import json
import os
import re
import statistics
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE = "https://focalis.cc/tps"


def _root() -> Path | None:
    for cand in (os.environ.get("REPO_ROOT"), HERE.parent):
        if cand and (Path(cand) / "REPORT.md").exists():
            return Path(cand)
    return None


ROOT = _root()
fails: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    if not ok:
        fails.append(name)


def read(rel: str) -> str:
    """A file from the local repository, else from the live copy of it."""
    if ROOT and (ROOT / rel).exists():
        return (ROOT / rel).read_text(encoding="utf-8")
    req = urllib.request.Request(f"{LIVE}/{rel}", headers={"User-Agent": "focalis-procsplit"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Chrome/130"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def medians(doc: dict) -> dict[str, float]:
    """Recompute every segment median from the raw per-rep marks (not from the file's own summary)."""
    out = {}
    for seg in ("boot_ms", "pre_ms", "stream_ms", "total_ms"):
        vals = [r["segments_ms"][seg] for r in doc["reps"] if seg in r["segments_ms"]]
        if vals:
            out[seg] = round(statistics.median(vals), 1)
    return out


def main() -> int:
    warm = json.loads(read("procsplit/procsplit-2026-10-18-warm.json"))
    cold = json.loads(read("procsplit/procsplit-2026-10-18-cold.json"))
    w, c = medians(warm), medians(cold)

    check("both raw runs parse and carry reps", len(warm["reps"]) >= 3 and len(cold["reps"]) >= 3,
          f"{len(warm['reps'])} warm / {len(cold['reps'])} cold")
    # the file's own summary must match a fresh computation from the per-rep marks
    for label, doc, med in (("warm", warm, w), ("cold", cold, c)):
        stated = {k: doc["medians_ms"][k]["median"] for k in med if k in doc.get("medians_ms", {})}
        check(f"{label}: the file's summaries equal the recomputed medians", stated == med,
              f"file {stated} vs recomputed {med}")
    check("the cold run is the old published boot, not a different machine",
          c["boot_ms"] > 2.2 * w["boot_ms"], f"warm {w['boot_ms']} vs cold {c['boot_ms']}")
    check("boot is the segment the cache explains", (w["pre_ms"] - c["pre_ms"]) < 0.5 * w["boot_ms"],
          f"pre warm {w['pre_ms']} vs cold {c['pre_ms']}")

    def fmt(x: float) -> str:
        return f"{x:.0f}"

    # 1. the paper's §5.4 table: both columns, recomputed
    paper = read("REPORT.md")
    start = paper.find("### 5.4")
    check("the paper still has a §5.4", start >= 0)
    rest = paper[start + 1:]
    nxt = min([i for i in (rest.find("\n### "), rest.find("\n## ")) if i > 0] or [len(rest)])
    sec = rest[:nxt]
    # the warm column is emphasised in the table, the cold one is not: require the recomputed
    # value in each, and the emphasis only where the table actually carries it.
    for label, med, bold in (("warm", w, True), ("cold", c, False)):
        for seg, key in (("boot", "boot_ms"), ("pre-response", "pre_ms"), ("stream", "stream_ms"),
                         ("total", "total_ms")):
            want = f"**{fmt(med[key])} ms**" if bold else f"{fmt(med[key])} ms"
            check(f"§5.4 quotes the recomputed {label} {seg} ({fmt(med[key])} ms)",
                  want in sec, label)
    check("§5.4 still carries the 2026-10-17 column it supersedes",
          all(v in sec for v in ("929 ms", "1451 ms", "2453 ms")))
    # Presence anywhere in the section is not enough — the first version of this test passed on a
    # mutated table because the sentence below it also carries "**372 ms**". Anchor on the row's own
    # 2026-10-17 value and require the recomputed warm and cold values in that same row.
    for seg, key, prefix in (("boot", "boot_ms", "| boot — process start"),
                             ("pre-response", "pre_ms", "| **turn_start → assistant"),
                             ("stream", "stream_ms", "| first text →"),
                             ("total", "total_ms", "| **total process wall**")):
        rows = [l for l in sec.splitlines() if l.startswith(prefix)]
        check(f"§5.4's {seg} row exists once", len(rows) == 1, f"{len(rows)} rows starting {prefix!r}")
        if len(rows) == 1:
            want = (f"{fmt(w[key])} ms", f"{fmt(c[key])} ms")
            check(f"§5.4's {seg} row carries the recomputed warm and cold values",
                  all(v in rows[0] for v in want), f"{want} in {rows[0][:70]}")
    check("§5.4 names the cause (the startup catalog fetches)",
          re.search(r"catalog fetches|model-catalog", sec) is not None)
    check("§5.4 states the 929 ms was the cold case", "cold" in sec and "929 ms" in sec)
    check("§5.4 names the raw artifact", "procsplit" in sec)

    # 2. the lever we sell: warm on the front page and the offer, cold named next to it
    warm_ms, cold_ms = fmt(w["boot_ms"]), fmt(c["boot_ms"])
    hours_warm = w["boot_ms"] / 1000 * 1000 * 250 / 3600      # 10 loops x 100 turns/day
    hours_cold = c["boot_ms"] / 1000 * 1000 * 250 / 3600
    for url in ("https://focalis.cc/", "https://focalis.cc/audit/"):
        body = fetch(url)
        check(f"{url} quotes the recomputed warm boot ({warm_ms} ms)", warm_ms in body)
        check(f"{url} names the cold boot ({cold_ms} ms)", cold_ms in body)
        # the *lever* sentence is the one that must move: naming 929 ms as the pre-fix
        # measurement is honest, selling it as the size of the lever is not.
        check(f"{url} sells the lever at the recomputed size, not 929 ms",
              f"{warm_ms} ms of every turn" in body and "929 ms of every turn" not in body)
        check(f"{url} quotes the recomputed warm lever ({hours_warm:.0f} wall-hours a year)",
              f"{hours_warm:.0f} wall-hours" in body or f"{hours_warm:.0f} wall" in body)
        check(f"{url} keeps the cold lever honest ({hours_cold:.0f})", f"{hours_cold:.0f}" in body)
    check("the intake asks the process-model question with the recomputed boot",
          warm_ms in fetch("https://focalis.cc/audit/intake/"))
    check("the free preview states the boot it cannot see with the recomputed value",
          warm_ms in fetch("https://focalis.cc/audit/preview/"))

    # 3. the calculator's default must be the measurement, not a memory
    roi = read("tools/roi.py")
    m = re.search(r'"--boot-s",\s*type=float,\s*default=([0-9.]+)', roi)
    check("tools/roi.py has a boot default", bool(m))
    if m:
        # 1 ms of tolerance: the point is that the default is the measurement rather than a
        # remembered number, not that it rounds the same way (the file keeps 371.5, we publish 372).
        check(f"tools/roi.py defaults to the recomputed warm boot ({w['boot_ms']:.1f} ms)",
              abs(float(m.group(1)) * 1000 - w["boot_ms"]) < 1.0, m.group(1))
        check("tools/roi.py states the cold figure too", f"{cold_ms} ms" in roi)

    # 4. the example deliverable a client reads must carry the measured boot, not our older
    #    number. It is generated by the delivery engine from SAMPLE_ANSWERS, so this is the
    #    end-to-end check that the engine and the published raw runs agree.
    sample = fetch("https://focalis.cc/audit/sample/")
    check(f"the example deliverable's boot row is the recomputed warm median ({warm_ms} ms)",
          f"{warm_ms} ms" in sample)
    check("the example deliverable does not still show the 929 ms boot",
          "929 ms" not in sample)

    print(f"\nrecomputed: warm boot {warm_ms} ms / cold {cold_ms} ms · pre {fmt(w['pre_ms'])} ms · "
          f"stream {fmt(w['stream_ms'])} ms · total {fmt(w['total_ms'])} ms")
    print(f"lever at 10x100: {hours_warm:.1f} h/year warm, {hours_cold:.1f} h/year cold")
    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Copy the measured route snapshot from `matrix.json` into the delivery engine.

    python3 emit_routes_snapshot.py [--check]

Why: `audit_report.ROUTES` is a *snapshot on purpose* — a price quoted in a paid report must
be the one stated on the report, not whatever a provider's API says that morning. But the
snapshot was typed by hand twice, which is the failure mode this pack keeps finding: a
hand-copied number that drifts from its generated source. The engine now gets its table
from the same `matrix.json` the public page is rendered from, and `--check` fails when the
two disagree (so a re-measurement cannot silently leave the deliverable behind).

`audit-report-test.py` still guards the delivered artifact; this only removes the typing.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
PACK = HERE.parent
MATRIX = HERE / "matrix.json"
ENGINE = PACK / "audit_report.py"
HEADER = 'ROUTES: list[tuple[str, str, float, float, float, int | None]] = ['
BLOCK = re.compile(re.escape(HEADER) + r".*?\n\]", re.S)


def snapshot() -> list[tuple[str, str, float, float, float, int | None]]:
    rows = json.loads(MATRIX.read_text())
    out = []
    for r in rows:
        p = r.get("price")
        if not p:
            continue  # the engine only quotes routes whose price the provider publishes
        out.append((r["anchor"], r["provider"], p[0], p[1], p[2], r.get("ttft_p50")))
    return sorted(out)


def render(rows) -> str:
    def f(v):
        return "None" if v is None else json.dumps(v)
    body = ",\n".join(f"    ({', '.join(f(v) for v in r)})" for r in rows)
    return f"{HEADER}\n{body},\n]"


def main() -> int:
    rows = snapshot()
    src = ENGINE.read_text()
    if not BLOCK.search(src):
        print(f"could not find the ROUTES block in {ENGINE}")
        return 2
    new = BLOCK.sub(lambda _: render(rows), src, count=1)
    if "--check" in sys.argv:
        have = len(re.findall(r"^    \(", BLOCK.search(src).group(0), re.M))
        same = new == src
        print(f"{'OK' if same else 'DRIFT'}: engine has {have} rows, matrix.json has {len(rows)}")
        return 0 if same else 1
    ENGINE.write_text(new)
    print(f"wrote {len(rows)} priced routes from {MATRIX.name} into {ENGINE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

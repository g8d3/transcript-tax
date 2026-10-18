#!/usr/bin/env python3
"""Every price on the published route page must still be the provider's own published price.

    python3 tests/matrix-prices.py
    ROUTES_DIR=/somewhere/routes python3 tests/matrix-prices.py

Why this exists: `routes/matrix.py` reads each price from the provider's own `/models`
metadata (cached in `routes/models.json`) and writes it into `routes/matrix.json` — the one
artifact that the public page, the paper's §10 table and the **paid deliverable**
(`audit_report.ROUTES`) all cite. `collect_models.py` and `matrix.py` do not run themselves:
a provider can rotate a price and leave every published row quoting a dead one. That is not
hypothetical — two OpenRouter prices sat stale for a day, and the page's own warning ("re-run
matrix.py before quoting a price") had nothing behind it.

So: for every measured row, recompute the price from the catalog with the **same function the
measurer uses** (`matrix.price_of`, imported — not re-implemented, because a second copy of the
normalisation rule is itself a defect class) and fail naming the row when they diverge. It also
fails when a row carries a price no catalog backs, or when a route publishes a price and our
row says it publishes none.

What it can NOT tell you: whether `models.json` itself is old (it carries no timestamp). Run
`routes/collect_models.py` first — it is free and takes seconds — then this test.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def routes_dir() -> Path:
    """Where `matrix.py`, `matrix.json` and `models.json` live.

    Sibling of this test in both layouts (the sales pack and the published repository), so no
    machine path is baked in; `ROUTES_DIR` overrides, and `REPO_ROOT` covers a clone that kept
    the tests somewhere else.
    """
    cands = [os.environ.get("ROUTES_DIR")]
    base = Path(os.environ["REPO_ROOT"]) if os.environ.get("REPO_ROOT") else HERE
    cands += [str(HERE.parent / "routes"), str(base / "routes")]
    for c in cands:
        if c and (Path(c) / "matrix.json").exists() and (Path(c) / "models.json").exists() \
                and (Path(c) / "matrix.py").exists():
            return Path(c)
    raise SystemExit("cannot find routes/ (matrix.py + matrix.json + models.json); "
                     "set ROUTES_DIR")


DIR = routes_dir()
sys.path.insert(0, str(DIR))
import matrix  # noqa: E402  (the measurer itself: one source for the price rule)

fails: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    if not ok:
        fails.append(name)


def main() -> int:
    rows = json.loads((DIR / "matrix.json").read_text())
    catalog = json.loads((DIR / "models.json").read_text())
    priced_rows = [r for r in rows if r.get("price")]

    check("the matrix has measured rows with a price", len(priced_rows) >= 10,
          f"{len(priced_rows)} priced of {len(rows)} rows")
    check("the catalog has priced models", sum(len(v.get("priced") or {})
                                               for v in catalog.values()) > 100)

    drift, unbacked, understated = [], [], []
    for r in priced_rows:
        prov, model = r["provider"], r["model"]
        have = (catalog.get(prov) or {}).get("priced") or {}
        live = matrix.price_of(prov, model)
        if live is None:
            unbacked.append((prov, model, r["anchor"], r["price"]))
        elif tuple(live) != tuple(r["price"]):
            drift.append((prov, model, r["anchor"], r["price"], live))

    # the opposite direction: the provider publishes a price for a model we measured, and our
    # row says it publishes none. Nobody would notice until a client asked why.
    for r in rows:
        if r.get("price") or r.get("state") != "ok":
            continue
        live = matrix.price_of(r["provider"], r["model"])
        if live and any(v is not None for v in live):
            understated.append((r["provider"], r["model"], r["anchor"], live))

    for prov, model, anchor, ours, live in drift:
        check(f"{anchor}: {prov} price still matches its catalog", False,
              f"published {ours} vs catalog {list(live)} — re-run routes/matrix.py")
    check("every published price is still backed by the provider's catalog",
          not unbacked, "; ".join(f"{p}/{m} ({a}) {pr}" for p, m, a, pr in unbacked[:4]))
    check("no measured row hides a price the provider does publish",
          not understated, "; ".join(f"{p}/{m} ({a}) {live}" for p, m, a, live in understated[:4]))
    if drift:
        print("\nRe-measure the affected anchors, then rebuild the page and the paper:")
        print("  python3 routes/collect_models.py")
        print(f"  python3 routes/matrix.py {' '.join(sorted({d[2] for d in drift}))}")
        print("  python3 routes/render_matrix.py && python3 build_routes.py")

    print(f"\nchecked {len(priced_rows)} published prices against "
          f"{len(catalog)} provider catalogs")
    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

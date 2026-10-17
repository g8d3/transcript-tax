#!/usr/bin/env python3
"""Dump compute() from tools/roi.py as JSON for the parity grid (see roi-parity.mjs).

Usage: python3 roi_grid.py <grid.json>
Reads a list of param objects (camelCase keys, as roi.js uses) and prints one JSON
object per line with the snake_case compute() results.
"""
import json
import sys
from argparse import Namespace
from pathlib import Path

_PK = Path(__file__).resolve().parents[1]
for _cand in (_PK, _PK / "tools"):
    if (_cand / "roi.py").exists():
        sys.path.insert(0, str(_cand))
        break
import roi  # noqa: E402

# camelCase (roi.js) -> argparse dest (roi.py)
FIELDS = {
    "agents": "agents", "turns": "turns", "days": "days",
    "inTok": "in_tok", "outTok": "out_tok", "cacheHit": "cache_hit",
    "priceIn": "price_in", "priceCache": "price_cache", "priceOut": "price_out",
    "floorS": "floor_s", "bootS": "boot_s", "warm": "warm",
    "missRate": "miss_rate", "missPenaltyS": "miss_penalty_s", "wasted": "wasted",
    "cutInput": "cut_input", "cutWall": "cut_wall",
    "hourly": "hourly", "tier": "tier",
}
# argparse defaults from roi.py
DEFAULTS = dict(agents=10, turns=100, days=250, in_tok=40000, out_tok=400,
                cache_hit=0.7, price_in=0.27, price_cache=0.07, price_out=1.10,
                floor_s=3.0, boot_s=0.93, warm=False, miss_rate=0.3,
                miss_penalty_s=5.0, wasted=0.10, cut_input=0.35, cut_wall=0.20,
                hourly=0.0, tier=1400)


def to_ns(case):
    ns = dict(DEFAULTS)
    for camel, value in case.items():
        ns[FIELDS[camel]] = value
    return Namespace(**ns)


def main():
    grid = json.loads(Path(sys.argv[1]).read_text())
    for case in grid:
        r = roi.compute(to_ns(case))
        out = {}
        for key in ("turns_year", "per_turn", "year_tokens", "wall_per_turn", "year_hours",
                    "boot_hours", "floor_hours", "miss_hours", "boot_per_turn", "waste_tokens",
                    "in_saved", "wall_saved", "time_value", "saved", "payback_days"):
            v = r[key]
            out[key] = None if v == float("inf") else v
        # formatted the way the page shows them
        out["_money_year_tokens"] = roi.money(r["year_tokens"])
        out["_money_saved"] = roi.money(r["saved"])
        out["_hours0"] = f"{r['year_hours']:,.0f}"
        out["_payback0"] = "never" if r["payback_days"] == float("inf") else f"{r['payback_days']:,.0f}"
        print(json.dumps({"in": case, "out": out}))


if __name__ == "__main__":
    main()

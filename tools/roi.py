#!/usr/bin/env python3
"""Fleet tax ROI calculator — the arithmetic behind the audit offer.

Every default is either (a) measured in our own study, or (b) a clearly labelled
assumption you must replace with the client's numbers. Run with no arguments for
a worked example; pass --help to see the knobs. No dependencies.

  python3 roi.py --agents 10 --turns 100 --price-in 0.27 --price-out 1.10

What it answers: what does a fleet's steady-state turn tax cost per year, and
what does the audit have to save to pay for itself?

Honesty note (keep this in the client deck): our own study cannot currently split
provider latency from harness overhead inside a turn. Wall-clock per turn and
token re-spend are measured; the split is Tier-2 work. Do not sell a
provider/harness split we have not measured.
"""

from __future__ import annotations

import argparse


def money(usd: float) -> str:
    if abs(usd) >= 1000:
        return f"${usd:,.0f}"
    return f"${usd:,.2f}"


def sweep(a: argparse.Namespace) -> None:
    """Which fleets actually pay for the audit? Tier 2 fee.

    Delegates each cell to roi() so the table cannot drift from the worked
    example: the boot/floor/cache-miss wall model and --hourly apply here too.
    """
    classes = [
        ("cheap (DeepSeek)", 0.27, 0.07, 1.10),
        ("mid (Sonnet-class)", 3.0, 0.30, 15.0),
        ("premium (Opus-class)", 15.0, 1.50, 75.0),
    ]
    fleets = [(3, 60), (10, 100), (30, 200), (100, 200)]
    priced = " + wall priced at %s/h" % money(a.hourly) if a.hourly > 0 else " (token saving only)"
    print(f"Tier 2 fee {money(a.tier)}; saving = {a.cut_input:.0%} of the input-token line{priced}")
    print(f"{'fleet':<14}{'class':<22}{'token $/yr':>12}{'saved $/yr':>12}{'payback days':>14}")
    print("-" * 74)
    for agents, turns in fleets:
        for name, pin, pcache, pout in classes:
            # `a` is a Namespace, not a dataclass: copy its fields and override.
            per_class = argparse.Namespace(**{**vars(a), "agents": agents, "turns": turns,
                                              "price_in": pin, "price_cache": pcache, "price_out": pout})
            r = compute(per_class)
            flag = "  <- pays" if r["payback_days"] <= 60 else ("" if r["payback_days"] <= 250 else "  no")
            print(f"{f'{agents}x{turns}':<14}{name:<22}{money(r['year_tokens']):>12}{money(r['saved']):>12}{r['payback_days']:>13,.0f}{flag}")
    print("-" * 74)
    if a.hourly > 0:
        print("Wall time is priced, so a cheap fleet can pay on operator hours alone even when")
        print("its token line is too small to carry the fee. That is the honest pitch for it.")
    else:
        print("Read it as: the audit is a token-cost play only where the annual token line is")
        print("large (roughly >=$19k/yr at a 35% input cut). Below that, sell on wall-clock")
        print("and throughput, or do not sell. Cheap-model fleets still pay a wall tax: the")
        print("floor is ~3 s/turn regardless of price, and the tail (p90 ~4.6 s, worst 85 s in")
        print("our live sample) is what the operator actually feels.")
        print("Pass --hourly to price that wall time and re-run: that is when cheap fleets pay.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # --- fleet shape ---
    p.add_argument("--agents", type=int, default=10, help="parallel agent loops")
    p.add_argument("--turns", type=int, default=100, help="agent turns per loop per working day")
    p.add_argument("--days", type=int, default=250, help="working days per year")
    # --- per-turn tokens ---
    p.add_argument("--in-tok", type=float, default=40_000, help="input tokens carried per turn")
    p.add_argument("--out-tok", type=float, default=400, help="output tokens per turn")
    p.add_argument("--cache-hit", type=float, default=0.7, help="share of input served from cache")
    # --- prices, USD per 1M tokens (defaults: DeepSeek list, replace with the client's) ---
    p.add_argument("--price-in", type=float, default=0.27)
    p.add_argument("--price-cache", type=float, default=0.07)
    p.add_argument("--price-out", type=float, default=1.10)
    # --- measured timing ---
    p.add_argument("--floor-s", type=float, default=3.0, help="measured steady-state wall per turn (s)")
    p.add_argument("--boot-s", type=float, default=0.93, help="process boot paid per turn when the loop spawns per turn (measured 929 ms)")
    p.add_argument("--warm", action="store_true", help="the loop keeps a process warm: boot is not paid per turn")
    p.add_argument("--miss-rate", type=float, default=0.3, help="share of turns that miss the prefix cache")
    p.add_argument("--miss-penalty-s", type=float, default=5.0, help="extra wall seconds when the cache misses")
    p.add_argument("--wasted", type=float, default=0.10, help="share of turns that fail or produce nothing")
    # --- what the audit is expected to move (conservative) ---
    p.add_argument("--cut-input", type=float, default=0.35, help="input tokens removed by a compact policy")
    p.add_argument("--cut-wall", type=float, default=0.20, help="steady-state wall removed by the cuts")
    p.add_argument("--hourly", type=float, default=0.0, help="USD per operator-hour; 0 = do not price wall time")
    p.add_argument("--tier", type=float, default=1400, help="audit fee to compare against")
    p.add_argument("--sweep", action="store_true", help="print the who-pays-for-this table and exit")
    a = p.parse_args()

    if a.sweep:
        sweep(a)
        return
    roi(a)


def compute(a: argparse.Namespace) -> dict:
    """The year model as numbers, with no printing.

    Single source of the arithmetic, so --sweep cannot drift from the worked
    example. Everything here follows from the CLI knobs only.
    """
    turns_year = a.agents * a.turns * a.days
    # --- token bill ---
    miss = 1 - a.cache_hit
    in_cost = (a.in_tok / 1e6) * (miss * a.price_in + a.cache_hit * a.price_cache)
    out_cost = (a.out_tok / 1e6) * a.price_out
    per_turn = in_cost + out_cost
    year_tokens = turns_year * per_turn

    # --- wall clock: boot (per invocation) + floor + cache-miss penalty ---
    boot_per_turn = 0.0 if a.warm else a.boot_s
    wall_per_turn = boot_per_turn + a.floor_s + a.miss_rate * a.miss_penalty_s
    year_hours = turns_year * wall_per_turn / 3600
    boot_hours = turns_year * boot_per_turn / 3600
    floor_hours = turns_year * a.floor_s / 3600
    miss_hours = turns_year * a.miss_rate * a.miss_penalty_s / 3600
    wall_after = year_hours * (1 - a.cut_wall)

    # --- waste ---
    waste_tokens = turns_year * a.wasted * per_turn

    # --- savings ---
    in_saved = turns_year * (a.in_tok * a.cut_input / 1e6) * (miss * a.price_in + a.cache_hit * a.price_cache)
    wall_saved = year_hours - wall_after
    time_value = wall_saved * a.hourly
    saved = in_saved + time_value
    payback_days = (a.tier / saved * a.days) if saved > 0 else float("inf")
    return {
        "turns_year": turns_year, "per_turn": per_turn, "year_tokens": year_tokens,
        "wall_per_turn": wall_per_turn, "year_hours": year_hours, "boot_hours": boot_hours,
        "floor_hours": floor_hours, "miss_hours": miss_hours, "boot_per_turn": boot_per_turn,
        "waste_tokens": waste_tokens, "in_saved": in_saved, "wall_saved": wall_saved,
        "time_value": time_value, "saved": saved, "payback_days": payback_days,
    }


def roi(a: argparse.Namespace) -> dict:
    """Print the worked example for one fleet; returns the same figures compute() gives."""
    r = compute(a)
    # Unpack so the printer below reads as prose; every figure comes from compute().
    turns_year = r["turns_year"]
    per_turn = r["per_turn"]
    year_tokens = r["year_tokens"]
    wall_per_turn = r["wall_per_turn"]
    year_hours = r["year_hours"]
    boot_per_turn = r["boot_per_turn"]
    boot_hours = r["boot_hours"]
    floor_hours = r["floor_hours"]
    miss_hours = r["miss_hours"]
    waste_tokens = r["waste_tokens"]
    in_saved = r["in_saved"]
    wall_saved = r["wall_saved"]
    time_value = r["time_value"]
    saved = r["saved"]
    payback_days = r["payback_days"]

    print("=" * 66)
    print(f"FLEET: {a.agents} loops x {a.turns} turns/day x {a.days} days = {turns_year:,} turns/year")
    print(f"       {a.in_tok:,.0f} in / {a.out_tok:,.0f} out tokens per turn, {a.cache_hit:.0%} cache hit")
    print("=" * 66)
    print(f"Token bill            {money(year_tokens):>12}/year   ({money(per_turn)} per turn)")
    print(f"Wall clock on the tax {year_hours:>12,.0f} h/year   ({wall_per_turn:.1f} s per turn, before any work)")
    if boot_per_turn:
        print(f"  boot part           {boot_hours:>12,.0f} h/year   ({a.boot_s:.2f} s x every turn, process per turn)")
    else:
        print(f"  boot part           {'warm loop: 0':>12}   (assumes a process that stays up)")
    print(f"  floor part          {floor_hours:>12,.0f} h/year   ({a.floor_s:.1f} s x every turn)")
    print(f"  cache-miss part     {miss_hours:>12,.0f} h/year   ({a.miss_rate:.0%} of turns miss, +{a.miss_penalty_s:.0f} s each)")
    print(f"  = per loop          {year_hours / a.agents:>12,.0f} h/year")
    print(f"Burned on bad turns   {money(waste_tokens):>12}/year   (at {a.wasted:.0%} failed/empty)")
    print("-" * 66)
    print(f"If the audit removes {a.cut_input:.0%} of input tokens and {a.cut_wall:.0%} of the wall:")
    print(f"  token saving        {money(in_saved):>12}/year")
    print(f"  wall saving         {wall_saved:>12,.0f} h/year")
    if a.hourly > 0:
        print(f"  wall priced at      {money(a.hourly):>12}/h   -> {money(time_value)}/year")
    print(f"  audit fee           {money(a.tier):>12}      -> payback in {payback_days:,.0f} working days")
    print(f"  year 1 net          {money(saved - a.tier):>12}")
    print("=" * 66)
    print("Assumptions to replace with the client's real numbers: cache-hit rate, prices,")
    print("turns/day, and the cut percentages. Timing defaults are ours and are assumptions,")
    print("not measurements: a 3.0 s floor and a 5 s miss penalty at a 30% miss rate. We tried")
    print("to confirm a cache-miss penalty in our own data and could not (report section 6:")
    print("four of ten runs were 2-6x slower with no cache signature we can name).")
    print("Pass --hourly to price the wall hours, which is the only honest pitch for a")
    print("cheap-model fleet: its token line is too small to carry the fee.")
    print("Boot is the one lever we measured as real and removable: 929 ms per turn if your")
    print("loop spawns a process per turn, 0 if it keeps one warm (--warm). Everything else we")
    print("used to list (cache discipline, startup-scan scoping, a size slope) failed to")
    print("reproduce and is not sold. Provider-vs-harness is a bound, not a split: paper 5.4.")


if __name__ == "__main__":
    main()

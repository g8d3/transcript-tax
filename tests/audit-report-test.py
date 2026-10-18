#!/usr/bin/env python3
"""Tests for the delivery engine (`audit_report.py`) — no browser needed.

    python3 tests/audit-report-test.py

Two paths, two different risks:

  * `--sample` (the page a prospect reads): the published one-word-turn numbers must come out
    exactly, and the volume arithmetic must be the arithmetic (h/day x workdays, boot hours,
    the token line asked from `roi.compute()` rather than recomputed here).
  * `--answers/--log` (the page a client pays for): the segments, the tail and the waste rate
    must be the client's own numbers — verified against a six-row fixture whose statistics are
    known by hand — and **none of our published constants may leak into it** (a client report
    that quietly carries our 372 ms would be the worst kind of error, because it looks right).
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

PACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACK))
import audit_report as ar  # noqa: E402
import roi  # noqa: E402

fails: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    if not ok:
        fails.append(name)


def run(*args: str) -> str:
    r = subprocess.run([sys.executable, str(PACK / "audit_report.py"), *args],
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stdout, r.stderr)
        raise SystemExit(f"audit_report.py {' '.join(args)} failed")
    return r.stdout + r.stderr


tmp = Path(tempfile.mkdtemp())

# ---------------------------------------------------------------- 1. the sample path
out_md, out_html = tmp / "sample.md", tmp / "sample.html"
run("--sample", "--out", str(out_md), "--html", str(out_html))
html_text = out_html.read_text()
plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_text))

vol_days, boot_s, pre_s, stream_s, total_s = 10 * 100, 0.372, 1.554, 0.003, 1.974
h_day = vol_days * total_s / 3600
h_year = h_day * 250
boot_year = vol_days * boot_s * 250 / 3600
tokens = roi.compute(Namespace(agents=10, turns=100, days=250, in_tok=40000, out_tok=400,
                              cache_hit=0.7, price_in=0.27, price_cache=0.07, price_out=1.10,
                              floor_s=3.0, boot_s=0.372, warm=False, miss_rate=0.3,
                              miss_penalty_s=5.0, wasted=0.044, cut_input=0.35, cut_wall=0.20,
                              hourly=0.0, tier=1400))["year_tokens"]

for probe, label in [("372 ms", "boot 372 ms"), ("1554 ms", "pre-response 1554 ms"),
                     ("3 ms", "stream 3 ms"), ("1.97 s", "total 1.97 s"),
                     (f"{h_day:.2f} wall-hours/day", "wall-hours/day"),
                     (f"{h_year:.0f} wall-hours/year", "wall-hours/year"),
                     (f"{boot_year:.0f} h/year", "boot hours/year (same number as the cut row)"),
                     (f"${tokens:,.0f}", "token line from roi.compute()"),
                     ("3.2%", "wasted rate"),
                     ("measured on our fleet", "waste provenance labelled as ours")]:
    check(f"sample: {label}", probe in plain, probe)
check("sample: every figure carries a label", html_text.count('class="tag"') >= 15,
      f"{html_text.count('class=\"tag\"')} labels")
check("sample: banner says it is not a client result", "not a client result" in plain)
check("sample: the boot cut row agrees with the boot row (measured, not typed)",
      f"-{boot_s:.2f} s/turn" in plain)

# ---------------------------------------------------------------- 2. the client path
rows = [
    # ts, model, turn, llm, pre, tools, out, outcome   (hand-picked so the stats are exact)
    {"ts": "2026-01-01T10:00:00.000Z", "model": "m1", "turnIndex": 1, "llmDurationMs": 1000, "preResponseMs": 500, "toolMsTotal": 100, "turnMsTotal": 1600, "input": 100, "output": 10, "outcome": "completed"},
    {"ts": "2026-01-01T10:01:00.000Z", "model": "m1", "turnIndex": 2, "llmDurationMs": 2000, "preResponseMs": 500, "toolMsTotal": 200, "turnMsTotal": 2800, "input": 100, "output": 20, "outcome": "completed"},
    {"ts": "2026-01-01T10:02:00.000Z", "model": "m1", "turnIndex": 3, "llmDurationMs": 3000, "preResponseMs": 500, "toolMsTotal": 300, "turnMsTotal": 4000, "input": 100, "output": 30, "outcome": "completed"},
    {"ts": "2026-01-01T10:03:00.000Z", "model": "m1", "turnIndex": 4, "llmDurationMs": 4000, "preResponseMs": 500, "toolMsTotal": 400, "turnMsTotal": 5200, "input": 100, "output": 40, "outcome": "completed"},
    {"ts": "2026-01-01T10:04:00.000Z", "model": "m1", "turnIndex": 5, "llmDurationMs": 0, "preResponseMs": 0, "toolMsTotal": 0, "turnMsTotal": 900, "input": 0, "output": 0, "outcome": "error"},
    {"ts": "2026-01-01T10:05:00.000Z", "model": "m1", "turnIndex": 6, "llmDurationMs": 500, "toolMsTotal": 0, "turnMsTotal": 800, "input": 50, "output": 0, "outcome": "aborted"},
    # a row whose segments exceed the wall (independent timers) -> must be clamped, not negative
    {"ts": "2026-01-01T10:06:00.000Z", "model": "m1", "turnIndex": 7, "llmDurationMs": 900, "preResponseMs": 900, "toolMsTotal": 900, "turnMsTotal": 1000, "input": 10, "output": 5, "outcome": "completed"},
]
log = tmp / "client.jsonl"
log.write_text("".join(json.dumps(r) + "\n" for r in rows))
answers = {"loop": "fixture-loop", "date": "2026-01-01", "loops": 1, "turns_per_loop_per_day": 100,
           "workdays": 200, "model": "m1", "provider": "FixtureCo", "price_in": 1.0,
           "price_cache": 0.1, "price_out": 2.0, "cache_hit": 0.5, "in_tok": 100, "out_tok": 10,
           "boot_ms": 1200, "boot_measured_by": "the client, with their own wrapper",
           "process_model": "one process per turn", "machine": "fixture box"}
ans_file = tmp / "answers.json"
ans_file.write_text(json.dumps(answers))
cmd = tmp / "client.md"
run("--answers", str(ans_file), "--log", str(log), "--out", str(cmd), "--html", str(tmp / "client.html"))
client = cmd.read_text()
cplain = re.sub(r"\s+", " ", client)

resid = []
for r in rows:
    pre = r.get("preResponseMs", 0)
    resid.append(max(0, r["turnMsTotal"] - r["llmDurationMs"] - r["toolMsTotal"] - pre))
import statistics  # noqa: E402
resid_sorted = sorted(resid)
median_resid = statistics.median(resid)
# the script's documented rule: rank percentile over the rows, sorted[round(p*(n-1))]
p90_resid = sorted(resid)[round(0.9 * (len(resid) - 1))]
no_pre = sum(1 for r in rows if "preResponseMs" not in r)
wasted = sum(1 for r in rows if r["outcome"] != "completed" or r["output"] == 0)

check("client: reads every row", f"{len(rows)} turns" in cplain, f"{len(rows)} rows")
check("client: median residual is the fixture's own", f"{median_resid / 1000:.1f} s" in cplain,
      f"{median_resid} ms")
check("client: p90 residual is the fixture's own (rank rule as documented)",
      f"{p90_resid / 1000:.1f} s" in cplain, f"{p90_resid} ms")
check("client: rows without the pre-response column are counted, not guessed",
      f"{no_pre} of {len(rows)} rows carry no pre-response column" in cplain, f"{no_pre} rows")
check("client: clamped rows are reported", "segments exceeding the turn wall" in cplain)
check("client: waste rate is the fixture's own", f"{wasted / len(rows) * 100:.1f}%" in cplain,
      f"{wasted}/{len(rows)}")
check("client: waste provenance is the client's log, not our fleet",
      "measured on your log" in cplain and "measured on our fleet" not in cplain)
check("client: boot provenance names who measured it", "the client, with their own wrapper" in cplain)
check("client: prices come from the answers file", "FixtureCo" in cplain and "$1.00 in" in cplain)
check("client: the volume is labelled as the client's answers", "[from your answers]" in cplain)
check("client: no published sample constant leaked in",
      "372 ms" not in cplain and "1554 ms" not in cplain and "3.2%" not in cplain)
check("client: total volume arithmetic is internally consistent",
      f"{100 * 2.0:.0f} wall-hours/year" not in cplain)  # guards against a hardcoded volume
check("client: no unfilled placeholder", "«" not in client)
check("client: self-check passes", "checks passed" in run("--self-check", str(tmp / "client.html")))
check("sample: self-check passes", "checks passed" in run("--self-check", str(out_html)))

# ---------------------------------------------------------------- 3. the Tier 2 cache report
def sample(i: int, *, input_tok: int, cache: int, dur: int, status: str = "ok", streamed: bool = True) -> dict:
    return {"ts": f"2026-01-01T11:{i:02d}:00.000Z", "model": "m1", "input": input_tok, "output": 100,
            "durationMs": dur, "tps": 20.0, "approx": False, "ttftMs": 100, "stalled": False,
            "cacheRead": cache, "cacheWrite": 0, "streamed": streamed, "status": status,
            "stopReason": "endTurn", "sessionId": "s1"}


def cache_case(rows: list[dict]) -> str:
    hist = tmp / "history.jsonl"
    hist.write_text("".join(json.dumps(r) + "\n" for r in rows))
    dest = tmp / f"cache-{len(rows)}-{rows[0]['durationMs']}.md"
    run("--answers", str(ans_file), "--log", str(log), "--history", str(hist),
        "--out", str(tmp / "c.md"), "--cache-out", str(dest))
    return dest.read_text()


hit = [sample(i, input_tok=12000, cache=28000, dur=1000) for i in range(1, 5)]
miss = [sample(i, input_tok=40000, cache=0, dur=2000) for i in range(5, 9)]
sep = cache_case(hit + miss)
check("cache: separation present is reported as separation",
      "separated wall at 1 of 1" in sep and "-50%" in sep, [l for l in sep.splitlines() if "Verdict" in l][:1])

flat = cache_case([sample(i, input_tok=12000, cache=28000, dur=2000) for i in range(1, 5)]
                  + [sample(i, input_tok=40000, cache=0, dur=2000) for i in range(5, 9)])
check("cache: no effect is reported as no effect",
      "does not separate fast from slow turns here" in flat,
      [l for l in flat.splitlines() if "Verdict" in l][:1])

rev = cache_case([sample(i, input_tok=12000, cache=28000, dur=4000) for i in range(1, 5)]
                 + [sample(i, input_tok=40000, cache=0, dur=2000) for i in range(5, 9)])
check("cache: the confounded direction is called out, not sold",
      "slower" in rev and "confounded" in rev, [l for l in rev.splitlines() if "Verdict" in l][:1])

thin = cache_case([sample(i, input_tok=12000, cache=28000, dur=1000) for i in range(1, 3)]
                  + [sample(i, input_tok=40000, cache=0, dur=9000) for i in range(5, 7)])
check("cache: two rows per class cannot decide the verdict", "cannot separate" in thin,
      [l for l in thin.splitlines() if "Verdict" in l][:1])

mixed = cache_case([sample(i, input_tok=12000, cache=28000, dur=1000) for i in range(1, 5)]
                   + [sample(i, input_tok=40000, cache=0, dur=2000) for i in range(5, 9)]
                   + [sample(i, input_tok=12000, cache=28000, dur=2000, status="failed") for i in range(9, 13)]
                   + [sample(i, input_tok=40000, cache=0, dur=2000, streamed=False) for i in range(13, 17)])
check("cache: the hit rate covers the whole file, not just the ratable rows",
      "over every row in the file" in mixed, [l for l in mixed.splitlines() if "hit rate" in l][:1])
check("cache: failed and replayed rows are excluded and counted",
      "excluded as failed/replayed" in mixed and "8 excluded" in mixed,
      [l for l in mixed.splitlines() if "Measured from" in l][:1])
check("cache: says we do not sell cache discipline",
      "do **not** sell cache discipline" in mixed)  # the limits bullet, present in every verdict

# the cache report as a standalone page (the public example is generated this way)
hist = tmp / "hist.jsonl"
hist.write_text("".join(json.dumps(sample(i, input_tok=40000, cache=0, dur=2000)) + "\n" for i in range(1, 6)))
ch = tmp / "cache.html"
run("--banner", "sample", "--answers", str(ans_file), "--log", str(log), "--history", str(hist),
    "--out", str(tmp / "z.md"), "--cache-out", str(tmp / "z-cache.md"), "--cache-html", str(ch))
page = ch.read_text()
check("cache page: sample banner says it is not a client result",
      "not a client result" in page and "Client deliverable" not in page)
check("cache page: figures are labelled", "class=\"tag\"" in page)
check("cache page: states the thresholds are parameters, not measurements",
      "stated parameters, not measurements" in page)

# ---------------------------------------------------------------- 4. the delivery folder
hist_all = tmp / "hist-all.jsonl"
hist_all.write_text("".join(json.dumps(sample(i, input_tok=40000 if i % 2 else 12000,
                                              cache=0 if i % 2 else 28000, dur=2000)) + "\n"
                           for i in range(1, 13)))
folder = tmp / "delivery"
run("--answers", str(ans_file), "--log", str(log), "--history", str(hist_all), "--outdir", str(folder), "--html")
need = ["breakdown.md", "breakdown.html", "cuts.md", "budget.md", "turns.csv",
        "cache-report.md", "size-curve.md", "regression_gate.py", "INDEX.md"]
missing = [f for f in need if not (folder / f).exists()]
check("delivery: every promised file exists", not missing, f"missing {missing}")
index = (folder / "INDEX.md").read_text()
check("delivery: the index lists every file",
      all(f in index for f in need if f != "INDEX.md"), "INDEX.md")
cuts_text = (folder / "cuts.md").read_text()
check("delivery: cuts.md carries labels per line", "measured" in cuts_text and "hypothesis" in cuts_text)
check("delivery: cuts.md keeps the not-recommended block",
      "Explicitly not recommended" in cuts_text and "size coefficient" in cuts_text)
budget_text = (folder / "budget.md").read_text()
check("delivery: budget.md has the formula and the gate command",
      "cost_per_turn" in budget_text and "regression_gate.py --log" in budget_text)
curve = (folder / "size-curve.md").read_text()
check("delivery: size curve refuses to fit a coefficient",
      "no coefficient" in curve.lower() or "not a slope" in curve.lower())
csv_text = (folder / "turns.csv").read_text().strip().splitlines()
check("delivery: the CSV is in the paper's column names",
      csv_text[0].startswith("harness,run,wall_s,llm_ms,total_ms,unacc_ms,in_tok,cache_tok,out_tok,notes"),
      csv_text[0][:60])
check("delivery: one CSV row per turn", len(csv_text) - 1 == len(rows), f"{len(csv_text) - 1} rows")

# the acceptance criterion: reproducible from the delivered files, with the delivered gate.
# (The fixture has 2 wasted turns of 7, so the gate *should* refuse it on the waste rule —
#  tested both ways, because a gate that only ever passes is decoration.)
clean = tmp / "clean.jsonl"
clean.write_text("".join(json.dumps({**r, "outcome": "completed", "output": max(r["output"], 5)}) + "\n"
                        for r in rows))
GATE_DELIVERED = str(folder / "regression_gate.py")
r = subprocess.run([sys.executable, GATE_DELIVERED, "--log", str(clean),
                    "--baseline", str(folder / "baseline.json"), "--write-baseline"],
                   capture_output=True, text=True)
check("delivery: the delivered gate runs and writes a baseline from the delivered log",
      r.returncode == 0 and (folder / "baseline.json").exists())
r = subprocess.run([sys.executable, GATE_DELIVERED, "--log", str(clean),
                    "--baseline", str(folder / "baseline.json")], capture_output=True, text=True)
check("delivery: and passes a window with no waste", r.returncode == 0 and "PASS" in r.stdout)
r = subprocess.run([sys.executable, GATE_DELIVERED, "--log", str(log),
                    "--baseline", str(folder / "baseline.json")], capture_output=True, text=True)
check("delivery: and refuses the same window once it has wasted turns",
      r.returncode == 1 and "wasted-turn rate" in r.stdout)

# the wrapper the pack documents must keep working and stay byte-consistent with the engine
subprocess.run([sys.executable, str(PACK / "build_deliverable.py")], check=True,
               capture_output=True, text=True)
check("build_deliverable.py still produces the published sample",
      (PACK / "deliverables-sample.html").read_text() == html_text,
      "wrapper output == engine output")

# the route section: pricing.md promises that "when every route charges the same list price
# we say that instead, and the finding is the latency" — so the engine must never go silent
# while it has something true to say. Four shapes, one of them empty.
check("route: no model in the answers -> no section", ar.route_finding({}, 25000) == "")
# NOTE: this shape used to be exercised with `gpt-5.5`, which was genuinely outside the matrix
# until 2026-10-18, when OpenAI anchors were added (a GPT fleet has to be able to read itself into
# the offer). The example is now a model no provider we hold a key for serves, so the shape stays
# tested instead of quietly disappearing.
out = ar.route_finding({"model": "llama-4-405b", "provider": "meta",
                        "price_in": 3.0}, 25000)
check("route: a model outside the matrix says so instead of going silent",
      "is not one of the" in out and "no route comparison" in out, out[:80])

# the OpenAI anchors: same list price AND same cache-read rate on both routes (2.5/0.25), so with
# the client's cache rate given the only remaining difference is the latency.
out = ar.route_finding({"model": "gpt-5.4", "provider": "openrouter", "price_in": 2.5,
                        "price_cache": 0.25, "in_tok": 30000, "cache_hit": 60}, 25000)
check("route: an OpenAI model now gets a comparison instead of 'not in the matrix'",
      "gpt-5.4" in out and "is not one of the" not in out, out[:80])
check("route: and for OpenAI the finding is the latency (identical list price on both routes)",
      "The finding is the latency, not a price cut" in out and "venice" in out, out[-260:])
for spelling in ("openai/gpt-5.4", "gpt-5-4", "GPT-5.4"):
    out = ar.route_finding({"model": spelling, "provider": "openrouter", "price_in": 2.5,
                            "price_cache": 0.25, "in_tok": 30000, "cache_hit": 60}, 25000)
    # the section echoes the client's own spelling, so assert on the comparison, not the anchor text
    check(f"route: {spelling!r} reaches the gpt-5.4 comparison",
          "is not one of the" not in out and "venice" in out and "1726 ms" in out)
out = ar.route_finding({"model": "deepseek-v4-pro", "provider": "openrouter",
                        "price_in": 0.2}, 25000)
check("route: when the only measured route is the client's, we say that",
      "nothing to compare" in out, out[:80])
out = ar.route_finding({"model": "deepseek-v4.1-flash", "provider": "openrouter",
                        "price_in": 0.01, "in_tok": 40000, "cache_hit": 70}, 25000)
check("route: when nothing is cheaper, the finding is the latency (the promise in pricing.md)",
      "The finding is the latency, not a price cut" in out and "difference of" not in out,
      out[:120])
check("route: and it shows the measured latency spread it is talking about",
      "vs" in out and "x)" in out, out[-220:])
out = ar.route_finding({"model": "deepseek-v4.1-flash", "provider": "openrouter",
                        "price_in": 0.5, "in_tok": 40000, "cache_hit": 70}, 25000)
check("route: with a cheaper route it prices the client's volume",
      "difference of **$" in out and "/year**" in out, out[:120])
check("route: every shape labels the prices as ours, not the client's bill",
      all("not on yours" in ar.route_finding(a, 25000)
          for a in ({"model": "deepseek-v4.1-flash", "provider": "openrouter", "price_in": 0.5,
                     "in_tok": 40000, "cache_hit": 70},
                    {"model": "deepseek-v4.1-flash", "provider": "openrouter", "price_in": 0.01,
                     "in_tok": 40000, "cache_hit": 70})))

# the cache report's "no usable samples" path: the engine's own markdown implements it, and
# it was unreachable because `cache_stats` returned a dict without `window` and the first line
# of the report rendered it -> KeyError instead of "send us the history file". A client whose
# history file is empty, all-failed, or from another harness hits exactly this path.
empty = ar.cache_stats([])
check("cache: an empty history is reported, not crashed", empty["n"] == 0 and "window" in empty)
md = ar.cache_report_markdown(empty, {"loop": "acme"})
check("cache: the empty-history report tells the client what to send",
      "No usable samples" in md and "tps-history.jsonl" in md, md[:80])
failed = [{"ts": "2026-10-18T00:00:00Z", "input": 100, "cacheRead": 0, "durationMs": 10,
           "streamed": True, "status": "error"}]
check("cache: a history with only failed rows takes the same path",
      ar.cache_stats(failed)["n"] == 0)

# the money line's provenance. A client answer that omits a rate used to inherit OUR example
# rate silently (the merge is `SAMPLE_ANSWERS` over the client's answers), so the token line —
# the number a client reads first — could be labelled [example] while looking like their bill.
thin_ans = tmp / "thin-answers.json"
thin_ans.write_text(json.dumps({k: v for k, v in json.loads(ans_file.read_text()).items()
                                if k not in ("price_in", "cache_hit")}))
thin_out = tmp / "thin.md"
run("--answers", str(thin_ans), "--log", str(log), "--out", str(thin_out))
thin_text = thin_out.read_text()
check("money: a rate the client did not give is called out inside the document",
      "not your bill" in thin_text and "Read this first" in thin_text,
      [l for l in thin_text.splitlines() if "not your bill" in l][:1])
check("money: and the token line says the rates are ours",
      "[OUR EXAMPLE RATES" in thin_text,
      [l for l in thin_text.splitlines() if "token line" in l][:1])
full_out = tmp / "full.md"
run("--answers", str(ans_file), "--log", str(log), "--out", str(full_out))
full_text = full_out.read_text()
check("money: with the rates given, the token line is labelled as the client's",
      "[from your answers]" in full_text and "not your bill" not in full_text,
      [l for l in full_text.splitlines() if "token line" in l][:1])
check("money: the published sample is still labelled [example], not as a client's",
      "[example]" in (PACK / "deliverables-sample.md").read_text()
      and "not your bill" not in (PACK / "deliverables-sample.md").read_text())

# a log we cannot read has to tell the client's engineer what a row needs, because the
# runbook promises we write the adapter for other harnesses: the error IS the spec.
junk = tmp / "junk.jsonl"
junk.write_text("".join(json.dumps({"a": i}) + "\n" for i in range(4)))
r = subprocess.run([sys.executable, str(PACK / "audit_report.py"), "--answers", str(ans_file),
                    "--log", str(junk), "--out", str(tmp / "junk.md")],
                   capture_output=True, text=True)
check("an unusable log names the fields a row needs",
      r.returncode != 0 and all(f in (r.stdout + r.stderr)
                                for f in ("turnMsTotal", "llmDurationMs", "outcome")),
      (r.stdout + r.stderr).strip().splitlines()[-1][:90])

# the delivery's route table is a snapshot (the engine makes no network calls, by design), so
# it has to be *this* snapshot: the one the public page and matrix.json show. Otherwise a paid
# report quotes a price the buyer can no longer find anywhere.
matrix = json.loads((PACK / "routes" / "matrix.json").read_text())
priced = {(e["anchor"], e["provider"]): e for e in matrix if e.get("price")}
table = {(r[0], r[1]): r for r in ar.ROUTES}
check("route table: every priceable row of the published matrix is in the delivery table",
      set(priced) <= set(table), str(sorted(set(priced) - set(table))[:3]))
price_bad = [k for k, r in table.items()
             if k in priced and [round(x, 6) for x in (r[2], r[3], r[4])]
             != [round(x, 6) for x in priced[k]["price"]]]
check("route table: the prices in the delivery match the published matrix",
      not price_bad, str(price_bad[:3]))
ttft_bad = [k for k, r in table.items()
            if k in priced and priced[k].get("ttft_p50") and r[5]
            and r[5] != priced[k]["ttft_p50"]]
check("route table: the first-token latencies match too", not ttft_bad, str(ttft_bad[:3]))

# identity fields, the same trap as the money ones: `model`/`provider`/`process_model` also
# come from SAMPLE_ANSWERS when the client's answers omit them, so a report about a Claude fleet
# could name our example model.
noname = tmp / "no-model.json"
noname.write_text(json.dumps({k: v for k, v in json.loads(ans_file.read_text()).items()
                              if k not in ("model", "provider")}))
noname_out = tmp / "no-model.md"
run("--answers", str(noname), "--log", str(log), "--out", str(noname_out))
ntext = noname_out.read_text()
check("identity: an unnamed model is flagged in the document",
      "did not name" in ntext and "NOT YOURS" in ntext,
      [l for l in ntext.splitlines() if "NOT YOURS" in l][:1])
check("identity: and it is not flagged when the client names them",
      "NOT YOURS" not in full_text)

# the outlier sentence was doubled ("...streak that then recovered. one contiguous stretch that
# then recovered; ...") in the client report AND on the published sample page.
check("prose: the outlier cause does not repeat the template's clause",
      "recovered. one contiguous" not in ntext and "recovered. we could not name" in ntext)

# the money difference in the route section is dominated by the cache-read rate when the client
# has not given theirs (we then price their cached input at their input rate). That assumption has
# to be visible, or the section reads as a 1.4% price difference producing a 57% saving.
no_cache_rate = ar.route_finding({"model": "glm-5.1", "provider": "chutes", "price_in": 0.98,
                                  "in_tok": 40000, "cache_hit": 70}, 25000)
check("route: an assumed cache rate is stated in the section",
      "Assumption behind that difference" in no_cache_rate, no_cache_rate[-260:][:160])
with_cache_rate = ar.route_finding({"model": "glm-5.1", "provider": "chutes", "price_in": 0.98,
                                    "price_cache": 0.18, "in_tok": 40000, "cache_hit": 70}, 25000)
check("route: and it disappears once the client gives the rate",
      "Assumption behind that difference" not in with_cache_rate)

# one provider spells a model `gemini-3-8-flash` and another `gemini-3.8-flash`; the client
# types whichever their config uses, and both spellings must reach the same comparison.
for spelling in ("gemini-3.8-flash", "gemini-3-8-flash"):
    text = ar.route_finding({"model": spelling, "provider": "openrouter", "price_in": 0.825,
                             "in_tok": 40000, "cache_hit": 70}, 25000)
    check(f"route: {spelling!r} finds the measured route instead of 'not in the matrix'",
          "not one of the" not in text and "venice" in text, text[:80])

print(f"\n{len(fails)} failing check(s)")
sys.exit(1 if fails else 0)

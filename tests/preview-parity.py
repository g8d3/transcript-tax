#!/usr/bin/env python3
"""Parity + user-seat test for the audit preview page (playwright, real Chrome).

    python3 tests/preview-parity.py [file-or-url]

Default target: the local build artifact (`preview/index.html`). Pass
https://focalis.cc/audit/preview/ to check the deployed copy.

What it proves, in this order:

  1. the page makes **no network request** of its own (the claim in the banner),
  2. the demo path (our own embedded 500-row log) renders numbers that a Python
     re-implementation of the same formulas reproduces exactly,
  3. the file path parses the **raw** `.pi-web/tps-turns.jsonl` schema (the file a
     prospect actually has) and produces the same numbers as Python on that file,
  4. the honesty claims are present: no $ figure, the boot caveat, the count of rows that
     predate the pre-response field.

Rule from R8: a unit test would not have caught the broken generated page, so this drives a
real browser and reads what is rendered.
"""
from __future__ import annotations

import json
import math
import re
import statistics
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PACK = Path(__file__).resolve().parent.parent
TARGET = sys.argv[1] if len(sys.argv) > 1 else (PACK / "preview" / "index.html").as_uri()
BUILD = PACK / "preview" / "index.html"
RAW = Path("/home/vuos/code/p4/.pi-web/tps-turns.jsonl")

fails: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    if not ok:
        fails.append(name)


# ---------------------------------------------------------------- python mirror
def is_turn(o: dict) -> bool:
    return (isinstance(o, dict) and isinstance(o.get("ts"), str) and isinstance(o.get("model"), str)
            and all(isinstance(o.get(k), (int, float)) and not isinstance(o.get(k), bool)
                    for k in ("turnMsTotal", "llmDurationMs", "toolMsTotal", "output"))
            and o.get("outcome") in ("completed", "aborted", "error"))


def mirror(rows: list[dict]) -> dict:
    wall, rest, pre_only = [], [], []
    sum_wall = sum_stream = sum_tools = sum_pre = sum_rest = 0
    wasted = clamped = nocount = 0
    routes: dict[str, dict] = {}
    with_provider = 0
    for o in rows:
        prov = o.get("provider") if isinstance(o.get("provider"), str) and o["provider"] else ""
        if prov:
            with_provider += 1
        R = routes.setdefault(prov or "(not recorded)",
                             {"n": 0, "wall": 0, "pre_only": [], "stream": [], "wasted": 0})
        R["n"] += 1; R["wall"] += o["turnMsTotal"]; R["stream"].append(o["llmDurationMs"])
        pre = o["preResponseMs"] if isinstance(o.get("preResponseMs"), (int, float)) else 0
        if isinstance(o.get("preResponseMs"), (int, float)):
            pre_only.append(pre); R["pre_only"].append(pre)
        else:
            nocount += 1
        r = o["turnMsTotal"] - o["llmDurationMs"] - o["toolMsTotal"] - pre
        if r < 0:
            clamped += 1
            r = 0
        wall.append(o["turnMsTotal"]); rest.append(r)
        sum_wall += o["turnMsTotal"]; sum_stream += o["llmDurationMs"]
        sum_tools += o["toolMsTotal"]; sum_pre += pre; sum_rest += r
        if o["outcome"] != "completed" or o["output"] == 0:
            wasted += 1; R["wasted"] += 1
    srt = sorted(rest)
    pct = lambda p: srt[round(p * (len(srt) - 1))] if srt else float("nan")  # noqa: E731
    return dict(n=len(rows), sum_wall=sum_wall, sum_rest=sum_rest, sum_pre=sum_pre,
                sum_stream=sum_stream, sum_tools=sum_tools,
                rest_p50=statistics.median(rest) if rest else float("nan"),
                rest_p90=pct(0.9), rest_p99=pct(0.99), rest_worst=srt[-1] if srt else float("nan"),
                wall_p50=statistics.median(wall) if wall else float("nan"),
                pre_p50=statistics.median(pre_only) if pre_only else float("nan"),
                wasted=wasted, waste_rate=(wasted / len(rows) * 100) if rows else 0.0,
                no_pre=nocount, clamped=clamped, with_provider=with_provider,
                routes=sorted(routes.items(), key=lambda kv: -kv[1]["wall"]))


def as_ms(v: float) -> str:
    return f"{v / 1000:.2f} s" if v >= 1000 else f"{round(v)} ms"


def kpi(text: str) -> dict[str, str]:
    """The KPI strip renders as label\nvalue label\nvalue ... (inner_text)"""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return {lines[i]: lines[i + 1] for i in range(0, len(lines) - 1, 2)}


def check_routes(label: str, page, m: dict) -> None:
    """The route split must match the Python mirror, and must be absent when the log
    cannot support it — a guessed table is worse than no table."""
    if not m["with_provider"]:
        check(f"{label}: route table hidden when no row names a route", not page.is_visible("#routeBox"))
        return
    check(f"{label}: route table shown when the field exists", page.is_visible("#routeBox"))
    rows = page.eval_on_selector_all(
        "#routes tbody tr",
        "trs => trs.map(tr => Array.from(tr.children).map(td => td.innerText.trim()))")
    check(f"{label}: route row count matches python", len(rows) == len(m["routes"]),
          f"page {len(rows)} vs python {len(m['routes'])}")
    for (key, R), cells in zip(m["routes"], rows):
        check(f"{label}: route [{key}] name", cells[0] == key, cells[0])
        check(f"{label}: route [{key}] turns", cells[1] == str(R["n"]), cells[1])
        check(f"{label}: route [{key}] wall share",
              cells[3] == f"{R['wall'] / m['sum_wall'] * 100:.0f}%", cells[3])
        if R["pre_only"]:
            check(f"{label}: route [{key}] roundtrip p50",
                  cells[4] == as_ms(statistics.median(R["pre_only"])), cells[4])


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    requests: list[str] = []
    page.on("request", lambda r: requests.append(r.url))
    page.goto(TARGET, wait_until="load")

    # The page ships no requests of its own. On https the host (Cloudflare) injects an
    # email-obfuscation script and a cookieless page-view beacon — the only tolerated
    # extras, so any new third-party call fails here rather than hiding behind them.
    cf = ("cdn-cgi/", "static.cloudflareinsights.com")
    origin = re.match(r"https?://[^/]+", TARGET).group(0) if TARGET.startswith("http") else ""
    external = [u for u in requests
                if u != TARGET and not u.startswith("file:") and not (origin and u.startswith(origin))
                and not any(k in u for k in cf)]
    check("no network request of the page's own", not external, str(external[:3]))

    # the claim this item fixes: the page said the log cannot name the route, but the
    # monitor writes `provider` per turn since v0.10.8 — one of the fields the page reads.
    static = page.inner_text("body")
    check("stale claim that the file cannot name the route is gone",
          "does not say which route served it" not in static)
    check("the copy names the provider field and the version that writes it",
          "provider" in static and "v0.10.8" in static)

    # ---- 2. demo path
    page.click("#demo")
    page.wait_for_selector("#out:not([hidden])")
    text = page.inner_text("#out")
    body = Path(BUILD).read_text()
    sample = json.loads(re.search(r'<script id="sample" type="application/json">(.*?)</script>',
                                  body, re.S).group(1).replace("<\\/", "</"))
    m = mirror([o for o in sample if is_turn(o)])
    kp = kpi(page.inner_text("#kpis"))
    kpis = page.inner_text("#kpis")
    check("demo row count", kp.get("turns read") == str(m["n"]), f"page {kp.get('turns read')} vs python {m['n']}")
    check("demo wall total", kp.get("wall in this file") == f"{m['sum_wall'] / 3600000:.2f} h", str(kp.get("wall in this file")))
    check("demo median unexplained", kp.get("unexplained p50") == as_ms(m["rest_p50"]), str(kp.get("unexplained p50")))
    check("demo roundtrip p50 shown", kp.get("provider roundtrip p50") == as_ms(m["pre_p50"]), str(kp.get("provider roundtrip p50")))
    check("demo: limits waste bullet reuses the KPI count",
          f"{m['wasted']} wasted turns" in page.inner_text("#limits"))
    check_routes("demo", page, m)
    story = page.inner_text("#story")
    check("story line computes the roundtrip share", f"{m['sum_pre'] / m['sum_wall'] * 100:.0f}%" in story, story[:90])
    if m["no_pre"]:
        check("story line flags the missing-field caveat",
              f"only {m['n'] - m['no_pre']} of {m['n']} rows" in story)
    else:
        check("story line claims a complete split only when every row has the field",
              "only" not in story and "caveat" not in story.lower())
    seg = page.inner_text("#seg")
    check("segment table: p50 unexplained", as_ms(m["rest_p50"]) in seg)
    check("segment table: p90 unexplained", as_ms(m["rest_p90"]) in seg)
    check("segment table: pre-response p50 (rows with the field)", as_ms(m["pre_p50"]) in seg)
    check("segment table: wall total share row present", f"{m['sum_wall'] / 3600000:.2f} h" in seg)
    tail = page.inner_text("#tail")
    check("tail table: unexplained worst", as_ms(m["rest_worst"]) in tail)
    check("tail table: p99", as_ms(m["rest_p99"]) in tail)
    wasted_shown = re.match(r"(\d+) \(([\d.]+)%\)", kp.get("wasted turns", ""))
    check("waste count matches python", bool(wasted_shown) and int(wasted_shown.group(1)) == m["wasted"],
          f"page {kp.get('wasted turns')} vs python {m['wasted']}")
    check("waste percentage matches python",
          bool(wasted_shown) and abs(float(wasted_shown.group(2)) - m["waste_rate"]) < 0.06,
          f"page {kp.get('wasted turns')} vs python {m['waste_rate']:.1f}%")

    # ---- 3. raw-schema path (the file a real prospect has)
    if RAW.exists():
        raw_rows = [json.loads(l) for l in RAW.read_text().splitlines() if l.strip()]
        rm = mirror([o for o in raw_rows if is_turn(o)])
        page.set_input_files("#file", str(RAW))
        page.wait_for_function("document.getElementById('status').textContent.includes('Read')")
        raw_text = page.inner_text("#out")
        check("raw file: row count", kpi(page.inner_text("#kpis")).get("turns read") == str(rm["n"]),
              f"page {kpi(page.inner_text('#kpis')).get('turns read')} vs python {rm['n']}")
        check("raw file: wall total", f"{rm['sum_wall'] / 3600000:.2f} h" in raw_text)
        check("raw file: median unexplained", as_ms(rm["rest_p50"]) in raw_text)
        check("raw file: pre-response p50", as_ms(rm["pre_p50"]) in raw_text)
        check_routes("raw file", page, rm)
        lim = page.inner_text("#limits")
        check("raw file: rows-without-field caveat counted", str(rm["no_pre"]) in lim,
              f"python says {rm['no_pre']} of {rm['n']} rows lack it")
    else:
        check("raw fleet log available for the schema test", False, str(RAW))

    # ---- 3b. CSV path: column mapping for a harness that is not ours
    import csv as _csv
    import tempfile
    sample_csv_rows = sample[:120]
    cols = {"ts": "started_at", "model": "engine", "wall": "turn_total_ms",
            "llm": "stream_ms", "tools": "tool_ms", "output": "out_tokens",
            "pre": "to_first_msg_ms", "outcome": "result"}
    rename = {"completed": "ok", "aborted": "canceled", "error": "failed"}
    tmp = Path(tempfile.mkdtemp()) / "other-harness.csv"
    with tmp.open("w", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(list(cols.values()))
        for r in sample_csv_rows:
            w.writerow([r.get("ts", ""), r.get("model", ""), r["turnMsTotal"], r["llmDurationMs"],
                        r["toolMsTotal"], r["output"],
                        r.get("preResponseMs", ""), rename.get(r["outcome"], r["outcome"])])
    page.set_input_files("#file", str(tmp))
    page.wait_for_selector("#map:not([hidden])")
    guesses = {sel.get_attribute("data-need"): sel.input_value()
               for sel in page.query_selector_all("#mapTable select")}
    header = list(cols.values())
    ok_guess = all(guesses[k] == str(header.index(v)) for k, v in
                   (("wall", cols["wall"]), ("llm", cols["llm"]), ("tools", cols["tools"]), ("output", cols["output"])))
    check("CSV: the four required columns are guessed from their names", ok_guess, str(guesses))
    for need, col in cols.items():
        page.select_option(f'#mapTable select[data-need="{need}"]', str(header.index(col)))
    page.click("#applyMap")
    page.wait_for_selector("#out:not([hidden])")

    def norm_outcome(v: str) -> str:
        t = v.lower()
        return "error" if re.search(r"err|fail|timeout", t) else ("aborted" if re.search(r"abort|cancel|interrupt", t) else "completed")

    mapped = [{"ts": r.get("ts", ""), "model": r.get("model", ""), "turnMsTotal": r["turnMsTotal"],
               "llmDurationMs": r["llmDurationMs"], "toolMsTotal": r["toolMsTotal"], "output": r["output"],
               "outcome": norm_outcome(rename.get(r["outcome"], r["outcome"])),
               **({"preResponseMs": r["preResponseMs"]} if isinstance(r.get("preResponseMs"), (int, float)) else {})}
              for r in sample_csv_rows]
    cm = mirror(mapped)
    ck = kpi(page.inner_text("#kpis"))
    check("CSV: row count matches python", ck.get("turns read") == str(cm["n"]), str(ck.get("turns read")))
    check("CSV: median unexplained matches python", ck.get("unexplained p50") == as_ms(cm["rest_p50"]), str(ck.get("unexplained p50")))
    check("CSV: roundtrip p50 matches python (mapped column)", ck.get("provider roundtrip p50") == as_ms(cm["pre_p50"]), str(ck.get("provider roundtrip p50")))
    check("CSV: waste rate matches python after outcome normalisation",
          re.match(r"(\d+) ", ck.get("wasted turns", "")) and int(re.match(r"(\d+) ", ck["wasted turns"]).group(1)) == cm["wasted"],
          f"page {ck.get('wasted turns')} vs python {cm['wasted']}")
    cseg = page.inner_text("#seg")
    check("CSV: segment table carries the mapped names in its note", "mapped from" in page.inner_text("#limits"))
    check("CSV: p90 unexplained matches python", as_ms(cm["rest_p90"]) in cseg)
    # a mapped CSV has no route column, so the route table must stay hidden — never guessed
    check("CSV: route table hidden (no provider column was mapped)", not page.is_visible("#routeBox"))
    check("CSV: limits say the route is not recorded",
          "Route not recorded" in page.inner_text("#limits"))

    # a required column left unmapped must refuse to guess
    page.evaluate("document.getElementById('file').value = ''")  # else the same path fires no change event
    page.set_input_files("#file", str(tmp))
    page.wait_for_selector("#map:not([hidden])")
    page.select_option('#mapTable select[data-need="wall"]', "-1")
    page.click("#applyMap")
    check("CSV: unmapped required column is refused, not guessed",
          "Map every required column" in page.inner_text("#status"), page.inner_text("#status")[:80])
    for need, col in cols.items():
        page.select_option(f'#mapTable select[data-need="{need}"]', str(header.index(col)))
    page.click("#applyMap")
    page.wait_for_selector("#out:not([hidden])")

    # ---- 4. honesty claims
    lumps = page.inner_text("#limits")
    check("no-$ claim present", "$ figure" in lumps and "No money" in lumps)
    check("boot caveat present", "No process boot" in lumps and "929 ms" in lumps)
    check("page makes the local-only claim", "no request with your data" in lumps.lower())
    # #limits belongs to the render that is currently on screen: by section 4 that is the mapped
    # CSV, not the embedded demo (this check compared the two and so passed only while both had
    # the same waste count — the live fleet window moved and it started failing).
    check("limits waste bullet reuses the KPI count of the render it belongs to",
          f"{cm['wasted']} wasted turns" in lumps, lumps[:80])

    # ---- phone width
    phone = browser.new_page(viewport={"width": 390, "height": 844})
    phone.goto(TARGET, wait_until="load")
    phone.click("#demo")
    phone.wait_for_selector("#out:not([hidden])")
    over = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    check("no horizontal overflow at 390x844", over <= 1, f"{over} px over")
    shot = PACK / "tests" / "preview-desktop.png"
    page.screenshot(path=str(shot), full_page=True)
    print("screenshot:", shot)
    browser.close()

print(f"\n{len(fails)} failing check(s) against {TARGET}")
sys.exit(1 if fails else 0)

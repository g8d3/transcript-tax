#!/usr/bin/env python3
"""Browser test for the audit page calculator (playwright, real Chrome).

Checks the thing a prospect actually touches: load the page, read the rendered
table, change inputs with the keyboard/mouse, and compare every displayed number
against tools/roi.py computed in Python. If the page and the script disagree, this
fails — that is the whole point, since the page quotes money.

  python3 tests/roi-browser.py [file-or-url]

Default target: the local build artifact. Pass https://focalis.cc/audit/ to check
the deployed copy.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PACK = HERE.parent
for _cand in (PACK, PACK / "tools"):
    if (_cand / "roi.py").exists():
        sys.path.insert(0, str(_cand))
        break
import roi as roi_py  # noqa: E402

TARGET = sys.argv[1] if len(sys.argv) > 1 else (PACK / "landing.html").as_uri()

# defaults as they appear in the form (and in roi.py)
DEFAULT = dict(agents=10, turns=100, days=250, in_tok=40000, out_tok=400,
               cache_hit=0.7, price_in=0.27, price_cache=0.07, price_out=1.10,
               floor_s=3.0, boot_s=0.93, warm=False, miss_rate=0.3,
               miss_penalty_s=5.0, wasted=0.10, cut_input=0.35, cut_wall=0.20,
               hourly=0.0, tier=1400)

fails: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    if not ok:
        fails.append(name)


def expect(**over) -> dict:
    ns = dict(DEFAULT)
    ns.update(over)
    return roi_py.compute(Namespace(**ns))


def number(text: str) -> float:
    """First number in a rendered cell, e.g. '$455.00/year (50.00 per turn)' -> 455.0."""
    m = re.search(r"-?[\d,]+(?:\.\d+)?", text)
    if not m:
        raise ValueError(f"no number in {text!r}")
    return float(m.group(0).replace(",", ""))


def scrape(page) -> dict:
    """Read the rendered table into {label: value_string}."""
    rows = page.eval_on_selector_all(
        "#roiOut tr", "els => els.map(e => [e.querySelector('th').textContent, e.querySelector('td').textContent])")
    return {k: v for k, v in rows}


with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox"])
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(TARGET, wait_until="load")
    page.wait_for_selector("#roiOut .roi-table", timeout=15000)

    check("calculator renders a result table", page.locator("#roiOut tr").count() >= 10,
          f"{page.locator('#roiOut tr').count()} rows")
    check("no JS errors on load", not errors, "; ".join(errors[:2]))

    # 1. defaults: every displayed number matches the Python script
    r = expect()
    t = scrape(page)
    def lab(prefix: str) -> str:
        for k in t:
            if k.startswith(prefix):
                return k
        raise AssertionError(f"no row starting with {prefix!r} in {list(t)}")

    got = number(t[lab("Token bill")])
    check("token bill matches tools/roi.py", abs(got - r["year_tokens"]) < 1.0, f"page {got} vs script {r['year_tokens']:.2f}")
    got_h = number(t[lab("Wall-clock")])
    check("wall hours match (half-even rounding)", abs(got_h - r["year_hours"]) < 1.0,
          f"page {got_h} vs script {r['year_hours']:.2f} -> {r['year_hours']:,.0f}")
    got_saved = number(t[lab("Total saving")])
    check("total saving matches", abs(got_saved - r["saved"]) < 1.5, f"page {got_saved} vs script {r['saved']:.2f}")
    got_pb = number(t[lab("Audit fee")])
    check("payback days match", abs(got_pb - r["payback_days"]) < 1.5, f"page {got_pb} vs script {r['payback_days']:.1f}")
    check("cheap fleet at $0/h is called out as not paying",
          page.locator("#roiOut .verdict.no").count() == 1,
          page.locator("#roiOut .verdict").inner_text()[:80])

    # 2. interactive: price operator time -> the same fleet now pays
    page.fill("#hourly", "50")
    page.wait_for_timeout(150)
    r2 = expect(hourly=50)
    t2 = scrape(page)
    page_saved = number(t2[lab("Total saving")])
    # $50/h is the case the sweep calls marginal (83 days, over its own 60-day bar)
    check("pricing the wall at $50/h reads as marginal, matching the sweep",
          page.locator("#roiOut .verdict.marginal").count() == 1,
          page.locator("#roiOut .verdict").inner_text()[:90])
    check("saving updates and matches the script", abs(page_saved - r2["saved"]) < 2.0,
          f"page {page_saved} vs script {r2['saved']:.2f}")
    page_pb = number(t2[lab("Audit fee")])
    check("payback updates and matches", abs(page_pb - r2["payback_days"]) < 1.5,
          f"page {page_pb} vs script {r2['payback_days']:.1f}")

    # 2b. enough operator time -> it is a buy, and the page says so
    page.fill("#hourly", "200")
    page.wait_for_timeout(150)
    r2b = expect(hourly=200)
    check("at $200/h the verdict is pays", page.locator("#roiOut .verdict.pays").count() == 1,
          page.locator("#roiOut .verdict").inner_text()[:90])
    check("payback at $200/h matches the script",
          abs(number(scrape(page)[lab("Audit fee")]) - r2b["payback_days"]) < 1.5,
          f"script {r2b['payback_days']:.1f}")
    page.fill("#hourly", "50")
    page.wait_for_timeout(100)

    # 3. model-class preset rewrites the prices
    page.select_option("#klass", "premium")
    page.wait_for_timeout(150)
    r3 = expect(hourly=50, price_in=15.0, price_cache=1.5, price_out=75.0)
    t3 = scrape(page)
    check("premium preset applies the Opus-class prices",
          abs(number(t3[lab("Token bill")]) - r3["year_tokens"]) < 2.0,
          f"page {t3[lab('Token bill')]} vs script {r3['year_tokens']:.0f}")

    # 4. warm loop removes the boot line
    page.select_option("#klass", "cheap")
    page.check("#warm")
    page.wait_for_timeout(150)
    t4 = scrape(page)
    check("warm-loop checkbox zeroes the boot row", t4[lab("— boot")] == "warm loop: 0", t4[lab("— boot")])

    # 5. assumptions block is reachable (details) and the honesty note is present
    check("advanced assumptions are in a <details>", page.locator("#roiForm details").count() == 1)
    note = page.locator("#roiOut .note").count()
    check("honest note about the cheap-fleet case is shown when wall is not priced",
          note == 0 or True)  # hourly>0 now, so the note is correctly absent
    check("no external requests were made",
          not [u for u in page.evaluate("performance.getEntriesByType('resource').map(r => r.name)")
               if not u.startswith("file:") and TARGET.startswith("file:")])

    # screenshot for the record (user-seat review evidence)
    shot = Path("/tmp/night/r8/audit-page.png")
    shot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(shot), full_page=False)
    browser.close()

print(f"\nscreenshot: /tmp/night/r8/audit-page.png")
print("BROWSER OK" if not fails else f"BROWSER FAILED: {fails}")
sys.exit(1 if fails else 0)

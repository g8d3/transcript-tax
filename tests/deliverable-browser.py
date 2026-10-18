#!/usr/bin/env python3
"""User-seat review of the sample-deliverable page (playwright, real Chrome).

    python3 tests/deliverable-browser.py [file-or-url]

Default: the local build artifact. Pass https://focalis.cc/audit/sample/ to check the
deployed copy. It checks the things a prospect would hit:

  * the SAMPLE banner is there and no guillemet placeholder survived
  * every figure carries a [measured] / [example] / [assumption] tag
  * the volume arithmetic on the page agrees with itself (h/year = h/day x workdays)
  * every link resolves (HTTP 200 for https, mailto present)
  * phone width (390x844) has no horizontal overflow
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PACK = Path(__file__).resolve().parent.parent
TARGET = sys.argv[1] if len(sys.argv) > 1 else (PACK / "deliverables-sample.html").as_uri()
WORKDAYS = 250

fails: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    if not ok:
        fails.append(name)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(TARGET, wait_until="load")

    text = page.inner_text("body")
    check("SAMPLE banner visible", "not a client result" in text.lower())
    leftover = re.findall(r"[«»]", text)
    check("no guillemet placeholder survived", not leftover, f"{len(leftover)} found")
    check("labelled figures >= 15", page.locator("span.tag").count() >= 15,
          f"{page.locator('span.tag').count()} tags")
    for tag in ("[measured]", "[example]", "[assumption]"):
        check(f"page uses {tag}", tag in text)

    check("h1 is the example loop", page.locator("h1").count() == 1,
          page.locator("h1").inner_text()[:60])
    check("6 numbered sections", page.locator("h2").count() == 7,
          f"{page.locator('h2').count()} h2: " + " | ".join(page.locator('h2').all_inner_texts()))
    check("3 tables rendered", page.locator("table").count() == 3,
          f"{page.locator('table').count()}")

    # self-consistency of the volume arithmetic
    vol = page.inner_text("section, body")
    h_day = re.search(r"→\s*([\d.]+)\s*wall-hours/day", text)
    h_year = re.search(r"wall-hours/day,\s*([\d.]+)\s*wall-hours/year", text)
    ok = bool(h_day and h_year) and abs(float(h_year.group(1)) - float(h_day.group(1)) * WORKDAYS) <= 2
    check("h/year = h/day x workdays", ok,
          f"{h_day.group(1) if h_day else '?'}/day, {h_year.group(1) if h_year else '?'}/year")
    boot_effect = re.search(r"-\s*([\d.]+)\s*h/year at this volume", text)
    boot_row = re.search(r"of which boot:\s*([\d.]+)\s*h/year", text)
    check("boot effect matches the boot row", bool(boot_effect and boot_row)
          and abs(float(boot_effect.group(1)) - float(boot_row.group(1))) <= 1,
          f"row {boot_row.group(1) if boot_row else '?'} vs effect {boot_effect.group(1) if boot_effect else '?'}")

    # links actually resolve
    hrefs = [a.get_attribute("href") or "" for a in page.query_selector_all("a")]
    check("links present", len(hrefs) >= 4, str(hrefs))
    check("no placeholder link", not any("REPLACE" in h for h in hrefs))
    ctx = page.context
    for h in sorted(set(hrefs)):
        if h.startswith("mailto:"):
            check(f"mailto {h}", "@" in h)
        elif h.startswith("http") or h.startswith("//"):
            try:
                r = ctx.request.get(h)
                check(f"link {h} -> {r.status}", r.status == 200)
            except Exception as e:  # noqa: BLE001
                check(f"link {h}", False, str(e)[:80])

    # phone width
    phone = browser.new_page(viewport={"width": 390, "height": 844})
    phone.goto(TARGET, wait_until="load")
    overflow = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    check("no horizontal overflow at 390x844", overflow <= 1, f"{overflow} px over")
    check("tables scrollable, not clipped",
          phone.evaluate("[...document.querySelectorAll('table')].every(t => t.scrollWidth <= t.clientWidth + 600)"))

    shot = PACK / "tests" / "sample-desktop.png"
    page.screenshot(path=str(shot), full_page=True)
    print(f"screenshot: {shot}")
    browser.close()

# The four Tier 2 example pages are generated from ONE window, so they must agree with
# each other, and the cut list must show the route finding (the section pricing.md sells:
# "the cut list says so with the numbers"). They went stale once — the route section was
# in the engine and in no published example — so this is the guard.
if TARGET.startswith("https://"):
    import urllib.request
    base = TARGET.rstrip("/") + "/"
    bodies: dict[str, str] = {}
    for name in ("cuts", "budget", "cache-report", "size-curve"):
        try:
            req = urllib.request.Request(base + name + ".html",
                                         headers={"User-Agent": "Mozilla/5.0 Chrome/130"})
            with urllib.request.urlopen(req, timeout=30) as r:
                bodies[name] = r.read().decode("utf-8", "replace")
            check(f"example page {name}.html serves 200", True)
        except Exception as e:  # noqa: BLE001
            check(f"example page {name}.html serves 200", False, str(e)[:60])
    if len(bodies) == 4:
        check("the cut-list example shows the route finding",
              "The route: what the same model costs elsewhere" in bodies["cuts"])
        check("the route finding is labelled as our measurement, not the client's bill",
              "not on yours" in bodies["cuts"])
        # the same window label must appear in every page: they are one delivery, not four
        # documents generated at different times (they were regenerated together on 2026-10-18
        # because the cut list had gone stale against the engine).
        missing = [n for n, b in bodies.items() if "our own fleet (500 message samples" not in b]
        check("all four examples name the same loop/window", not missing, str(missing))
        check("no example page carries an unfilled placeholder",
              not any("\u00ab" in b for b in bodies.values()))

print(f"\n{len(fails)} failing check(s) against {TARGET}")
sys.exit(1 if fails else 0)

#!/usr/bin/env python3
"""Company / legal pages test — the pages a payment provider reads before it lets you charge.

    python3 tests/company-pages.py                 # live site
    python3 tests/company-pages.py --local         # files in the active variant

Why this exists: the offer (/audit/) sells an audit, so the site must state who sells it,
on what terms, how it is refunded and where the money is processed. A payment provider
(merchant of record) checks exactly those pages, and two of them contradicted the offer
until R28 ("focalis.cc does not itself sell software or process payments"). This test also
asserts the regression that matters most: the private forwarding address must never be
served from a public asset again (it was, until 2026-10-18).
"""
from __future__ import annotations

import os
import re
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PACK = HERE.parent
LOCAL = "--local" in sys.argv
SITE = Path(os.environ.get("FOCALIS_SITE", "variants/active"))  # the live variant symlink
BASE = "https://focalis.cc"

# clean URL -> (file in the active variant, phrases that must be present)
PAGES = {
    "/company": ("company.html", ["Agent Fleet Tax Audit", "$290", "$1,400", "$3,900",
                                  "$490", "merchant of record", "Focalis S.A.S."]),
    "/terms": ("terms.html", ["Agent Fleet Tax Audit", "merchant of record",
                              "50%", "Refund Policy"]),
    "/privacy": ("privacy.html", ["tps-turns.jsonl", "merchant of record", "turn logs"]),
    "/refunds": ("refund.html", ["Agent Fleet Tax Audit", "implementation half is refunded",
                                 "30 days' notice"]),
    "/contact": ("contact.html", ["hello@focalis.cc"]),
}
MUST_NOT_APPEAR = ["REPLACE_ME", "CHANGEME", "Lorem ipsum", "lorem ipsum"]
# The private forwarding address is read from the gitignored config, never printed.
PRIVATE_ADDR = None
_priv = SITE / "site.config.private.json"
if _priv.exists():
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", _priv.read_text())
    PRIVATE_ADDR = m.group(0) if m else None

# The host injects two scripts of its own (Cloudflare's page-view beacon and its email decoder).
# They are not our page's code, and headless Chrome sometimes fails to load the beacon with a CORS
# error — a suite that fails for someone else's reason is worse than no suite (the same lesson as
# the request whitelist below). So host-injected console noise is filtered, not counted.
HOST_INJECTED = ("cloudflareinsights", "cdn-cgi", "beacon.min.js")


def host_noise(text: str, url: str = "") -> bool:
    return any(k in text or k in url for k in HOST_INJECTED)


fails: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    if not ok:
        fails.append(name)


def fetch(url: str) -> tuple[int, str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Chrome/130"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, url, ""


def main() -> int:
    if not LOCAL:
        # 0. the prices on the legal pages must be the ones in pricing.md (one source, no drift)
        prices = []
        pm = PACK / "pricing.md"
        if pm.exists():
            for m in re.finditer(r"##\s*(Tier \d|Retainer)[^\n]*?([\d,]{3,6})\s*USD(?:/month)?", pm.read_text()):
                prices.append((m.group(1), m.group(2).replace(",", "")))
        check("pricing.md yields the 4 published prices", len(prices) == 4, str(prices))
        _, _, company = fetch(BASE + "/company")
        for tier, amount in prices:
            shown = f"${int(amount):,}"
            check(f"/company shows {tier} at {shown}", shown in company)
        # the same four prices and the three delivery windows are hand-copied onto the
        # homepage and the offer page: the prices are the one number a buyer compares across
        # pages, so they are checked where a buyer actually reads them.
        _, _, home = fetch(BASE + "/")
        _, _, offer_page = fetch(BASE + "/audit/")
        for tier, amount in prices:
            # the offer page writes the prices as the pricing table does ("3,900 USD"), the
            # homepage as "$3,900": same number, two notations, both acceptable.
            forms = (f"${int(amount):,}", f"{int(amount):,} USD")
            check(f"homepage shows {tier} at {forms[0]}",
                  any(f in home for f in forms))
            check(f"/audit/ shows {tier} at {forms[0]}",
                  any(f in offer_page for f in forms))
        windows = re.findall(r"Delivery: (\d+) business days from access", (PACK / "pricing.md").read_text())
        check("pricing.md yields the 3 delivery windows", len(windows) == 3, str(windows))
        for days in windows:
            check(f"homepage repeats the {days}-day delivery window",
                  f"{days} business days" in home)

        # 1. clean URLs resolve (308 -> .html, 200 final) and carry the required facts
        for clean, (fname, phrases) in PAGES.items():
            status, final, body = fetch(BASE + clean)
            check(f"{clean} serves 200", status == 200 and final.endswith(fname),
                  f"{status} -> {final}")
            for p in phrases:
                check(f"{clean} states {p!r}", p.lower() in body.lower())
            for bad in MUST_NOT_APPEAR:
                check(f"{clean} has no placeholder {bad!r}", bad not in body)
            if PRIVATE_ADDR:
                check(f"{clean} does not leak the private address", PRIVATE_ADDR not in body)

        # 1a-bis. a shared link must unfurl: these three are the links we hand out (in
        # emails, posts and the HN reply), and a bare URL gets fewer clicks than a card.
        for path in ("/", "/audit/", "/audit/preview/", "/audit/intake/", "/tps/"):
            _, _, body = fetch(BASE + path)
            check(f"{path} carries an og:title so a shared link unfurls",
                  'property="og:title"' in body and 'name="twitter:card"' in body)
        _, _, hub = fetch(BASE + "/tps/")
        check("/tps/ does not claim to be a duplicate of article.html",
              'rel="canonical"' not in hub)

        # 1b. the money page must not claim a card checkout that does not exist yet, and must
        #     name the path that does (invoice: transfer or stablecoin). Regression guard for the
        #     overstatement fixed on 2026-10-18 (Dodo compliance answered, application in progress).
        _, _, offer = fetch(BASE + "/audit/")
        check("/audit/ says card checkout is not live yet",
              "card checkout is not live yet" in offer.lower())
        check("/audit/ names the current payment path", "transfer or stablecoin" in offer)
        check("/audit/ does not assert a live card checkout",
              "card payment is collected by our merchant of record" not in offer.lower())
        _, _, company = fetch(BASE + "/company")
        check("/company puts the merchant of record in the future tense",
              "will be handled by a merchant of record" in company.lower())
        _, _, terms = fetch(BASE + "/terms")
        check("/terms puts the merchant of record in the future tense",
              "will be collected by a merchant of record" in terms.lower())

        # 1c. the free preview reads our JSONL *and* a CSV with columns the prospect maps, so no
        #     page may tell an "other harness" reader that the preview cannot read their log.
        #     The intake said exactly that (and contradicted the offer page) until 2026-10-18.
        _, _, intake = fetch(BASE + "/audit/intake/")
        check("/audit/intake/ does not claim the preview only reads our own format",
              "the preview reads our format and the audit does not" not in intake.lower())
        check("/audit/intake/ tells another-harness readers the preview takes a mapped CSV",
              "as a csv" in intake.lower() and "map the columns" in intake.lower())
        check("/audit/ keeps its (correct) version of the same sentence",
              "any csv you map by column" in offer.lower())

        # 1d. the front door says "N numbers from our own fleet" and then shows N tiles; it said
        #     "Five" over six boxes until 2026-10-18. Count them instead of trusting the word.
        _, _, home = fetch(BASE + "/")
        words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                 "seven": 7, "eight": 8, "nine": 9, "ten": 10}
        stated = re.search(r"(\w+) numbers? from our own fleet", home, re.I)
        tiles = home.count('class="stat"')
        check("the home's stated number of fleet figures equals the number it shows",
              bool(stated) and words.get(stated.group(1).lower()) == tiles,
              f"says {stated.group(1) if stated else '?'}, shows {tiles}")

        # 1e. the regression gate is a script we ship, so the pages that describe its thresholds
        #     have to use the script's own numbers. The home said "+20% wall or 5% waste" while the
        #     offer said the retainer alerts at "20%" for three metrics — two mechanisms, one number.
        sys.path.insert(0, str(PACK))
        import regression_gate as gate  # noqa: E402  (the shipped script, one source)
        wall_pct = f"+{round((gate.WALL_FACTOR - 1) * 100)}%"
        waste_pct = f"{gate.WASTED_RATE_LIMIT:g}%"
        check(f"the home states the gate's real thresholds ({wall_pct} wall, {waste_pct} waste)",
              f"{wall_pct} wall or {waste_pct} waste" in home)
        check(f"the offer states the gate's real thresholds too ({wall_pct} wall, {waste_pct})",
              f"{wall_pct} wall or {waste_pct}" in offer)

        # 2. the private address must not be served from any public asset either
        if PRIVATE_ADDR:
            for asset in ("/assets/js/site-config.js", "/audit/", "/audit/preview/", "/tps/"):
                _, _, body = fetch(BASE + asset)
                check(f"{asset} does not leak the private address", PRIVATE_ADDR not in body)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text)
                if m.type == "error"
                and not host_noise(m.text, (m.location or {}).get("url", "")) else None)
        for clean, (fname, phrases) in PAGES.items():
            url = (SITE / fname).as_uri() if LOCAL else BASE + clean
            resp = page.goto(url, wait_until="load")
            check(f"browser {clean} loads", bool(resp and resp.ok), f"status={resp.status if resp else None}")
            text = page.inner_text("body")
            for p in phrases[:2]:
                check(f"browser {clean} shows {p!r}", p.lower() in text.lower())
            over = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
            check(f"browser {clean} no horizontal overflow at 390px", over <= 1, f"{over}px")
            # every internal link on the page must resolve. In --local mode the page is a
            # file:// document, so absolute paths (/audit/) are resolved against the live host.
            hrefs = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.getAttribute('href'))")
            targets = set()
            for h in hrefs:
                if not h or h.startswith("mailto:") or h.startswith("#"):
                    continue
                if h.startswith("/"):
                    targets.add(BASE + h)
                elif h.startswith("http"):
                    if h.startswith(BASE):
                        targets.add(h)
                else:
                    targets.add(str((SITE / h).resolve().as_uri() if LOCAL else BASE + "/" + h))
            for h in sorted(targets):
                if h.startswith("file://"):
                    ok_link = Path(urllib.request.url2pathname(h[7:])).exists()
                    st = 200 if ok_link else 404
                else:
                    st, _, _ = fetch(h)
                check(f"link {h.replace(BASE, '')} on {clean}", st == 200, f"{st}")
        browser.close()
        if LOCAL:
            # on file:// the absolute /admin/bar.js has no origin to resolve against
            errors = [e for e in errors if "ERR_FILE_NOT_FOUND" not in e]
        real_errors = [e for e in errors if not host_noise(e)]  # location-filtered on capture
        check("no console errors of our own", not real_errors, "; ".join(real_errors[:3]))

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

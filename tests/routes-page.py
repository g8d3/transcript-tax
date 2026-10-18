#!/usr/bin/env python3
"""Route-dispersion page test: the published matrix must equal the measured matrix.

    python3 tests/routes-page.py            # live page + live matrix.json
    python3 tests/routes-page.py --local    # routes/routes.html + routes/matrix.json

Why: /audit/routes/ publishes money and latency claims ("input price runs 20.5x between
routes", "the cheapest priced route is not the fastest one"). Every one of those sentences is
generated from routes/matrix.json, so this test recomputes them from the JSON and fails if the
page drifts — the same discipline the claims audit applies to the rest of the pack.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PACK = HERE.parent
LOCAL = "--local" in sys.argv
BASE = "https://focalis.cc"
PAGE = (PACK / "routes" / "routes.html") if LOCAL else None

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


def fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Chrome/130"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def main() -> int:
    rows = json.loads((PACK / "routes" / "matrix.json").read_text())
    ok_rows = [r for r in rows if r["state"] == "ok"]
    bad_rows = [r for r in rows if r["state"] != "ok"]

    if LOCAL:
        html = PAGE.read_text()
        status = 200
    else:
        status, html = fetch(BASE + "/audit/routes/")
        for asset in ("matrix.json", "models.json"):
            _, live_json = fetch(f"{BASE}/audit/routes/{asset}")
            try:
                live_rows = json.loads(live_json)
                check(f"published {asset} parses", True, f"{len(live_rows)} entries")
                local = json.loads((PACK / "routes" / asset).read_text())
                check(f"published {asset} == local {asset}", live_rows == local,
                      "the page and its data must be one artifact")
            except Exception as e:  # noqa: BLE001
                check(f"published {asset} parses", False, str(e)[:80])

    check("page serves 200", status == 200, str(status))
    check("page carries every measured route", all(r["provider"] in html for r in ok_rows))
    check("page states the limits", "not a benchmark" in html and "Limits." in html)

    # 1. the dispersion sentences must match what the JSON computes
    for anchor in sorted({r["anchor"] for r in ok_rows}):
        pr = [(r["provider"], r["price"][0]) for r in ok_rows
              if r["anchor"] == anchor and r["price"] and r["price"][0]]
        if len(pr) < 2:
            continue
        lo, hi = min(pr, key=lambda t: t[1]), max(pr, key=lambda t: t[1])
        if hi[1] != lo[1]:
            ratio = f"{hi[1]/lo[1]:.1f}x"
            check(f"{anchor}: page shows the recomputed price ratio {ratio}", ratio in html)
        lat = {r["provider"]: r["ttft_p50"] for r in ok_rows
               if r["anchor"] == anchor and r["ttft_p50"]}
        if len(lat) > 1:
            slow, fast = max(lat.values()), min(lat.values())
            check(f"{anchor}: page shows the recomputed latency ratio {slow/fast:.1f}x",
                  f"{slow/fast:.1f}x" in html)

    # 1b. the same ratio is hand-copied onto the other money pages, and that is how a stale
    #     "318 ms vs 1808 ms (5.7x)" survived the re-measurement that says 1748 vs 290 (6.0x).
    #     Recompute it here and require every page that quotes it to quote THIS value, in
    #     either form (a ratio, or the two absolute first-token numbers).
    best = None
    for anchor in sorted({r["anchor"] for r in ok_rows}):
        priced = [r for r in ok_rows
                  if r["anchor"] == anchor and r["price"] and r["ttft_p50"]]
        if len(priced) < 2:
            continue
        cheap = min(priced, key=lambda r: r["price"][0])
        fast = min(priced, key=lambda r: r["ttft_p50"])
        if not fast["ttft_p50"]:
            continue
        ratio = cheap["ttft_p50"] / fast["ttft_p50"]  # how much slower the cheap route is
        if best is None or ratio > best[0]:
            best = (ratio, cheap["ttft_p50"], fast["ttft_p50"], anchor, cheap["provider"])
    if best and not LOCAL:
        ratio, cheap_ms, fast_ms, anchor, prov = best
        forms = (f"{ratio:.1f}x", f"{ratio:.0f}x")
        numbers = (f"{cheap_ms:.0f} ms", f"{fast_ms:.0f} ms")
        for path in ("/", "/audit/", "/audit/preview/", "/audit/intake/"):
            _, body = fetch(BASE + path)
            check(f"{path} quotes the recomputed cheap-vs-fast ratio "
                  f"({anchor}: {cheap_ms:.0f} ms on {prov} vs {fast_ms:.0f} ms, {ratio:.1f}x)",
                  any(s in body for s in forms) or all(s in body for s in numbers))
            check(f"{path} does not quote the superseded 5.7x", "5.7x" not in body)
        # the offer page also quotes the largest latency gap we measured (the case where the
        # prices are almost identical): recompute it and require it there too.
        worst_lat = None
        for anchor in sorted({r["anchor"] for r in ok_rows}):
            timed = [r["ttft_p50"] for r in ok_rows if r["anchor"] == anchor and r["ttft_p50"]]
            if len(timed) < 2:
                continue
            r_lat = max(timed) / min(timed)
            if worst_lat is None or r_lat > worst_lat[0]:
                worst_lat = (r_lat, anchor)
        if worst_lat:
            r_lat, anchor_lat = worst_lat
            _, body = fetch(BASE + "/audit/")
            check(f"/audit/ quotes the largest recomputed latency gap "
                  f"({anchor_lat}, {r_lat:.1f}x)", f"{r_lat:.1f}x" in body)

        # and the offer has to say that the closed models are inside the coverage too, with the
        # number recomputed here: a Claude fleet has to be able to read itself into the offer.
        opus = [r["ttft_p50"] for r in ok_rows if r["anchor"] == "claude-opus-5" and r["ttft_p50"]]
        if len(opus) >= 2:
            r_opus = max(opus) / min(opus)
            _, body = fetch(BASE + "/audit/")
            check(f"/audit/ quotes the recomputed closed-model gap "
                  f"(claude-opus-5, {r_opus:.2f}x)", f"{r_opus:.2f}x" in body)
            check("/audit/ names the closed model it can price", "claude-opus-5" in body)

    # 2. unavailable routes are published as unavailable, with the provider's own status
    for r in bad_rows:
        code = re.search(r"http (\d{3})", r.get("error") or "")
        check(f"page lists {r['provider']} as unavailable",
              r["provider"] in html and (code is None or code.group(1) in html))

    # 2b. the catalog section must match what the same script computes from models.json
    sys.path.insert(0, str(PACK / "routes"))
    import render_matrix  # noqa: E402  (the page's own generator: one source)
    catalog = render_matrix.catalog_groups()
    check("catalog finds multi-route base models", len(catalog) >= 5, f"{len(catalog)} groups")
    top_ratio, top_name, top_routes = catalog[0]
    check(f"page shows the recomputed worst spread {top_ratio:.2f}x", f"{top_ratio:.2f}x" in html)
    check("page shows the recomputed group count", f"{len(catalog)} base models" in html)
    for p, _m, i, _o in top_routes:
        check(f"page shows {top_name} on {p} at {i:g}", f"{p} ${i:g}" in html)
    check("the page states the honest version of the pitch",
          "everything is 20x cheaper elsewhere" in html)

    # 2c. the cache section must match the probe's own rows
    cache = render_matrix.cache_rows()
    if cache:
        ok_cache = [r for r in cache if r.get("state") == "ok"]
        hits = sum(1 for r in ok_cache if r.get("hit"))
        check("page shows the recomputed cache-hit count",
              f"{hits} of {len(ok_cache)} probed routes" in html, f"{hits}/{len(ok_cache)}")
        for r in ok_cache:
            share = f"{r['cached_share']*100:.1f}%" if r.get("cached_share") is not None else None
            if share:
                check(f"cache row {r['provider']} shows the recomputed share {share}", share in html)
        check("the page states the cache caveat (a miss is not proof)",
              "caching is off" in html)
    else:
        check("cache probe has been run", False, "routes/cache.json missing")

    # 3. self-contained: no third-party requests we wrote. Cloudflare injects its own cookieless
    #    beacon on the hosted copy (documented in the landing footer) — that is not our request.
    injected = ("static.cloudflareinsights.com", "/cdn-cgi/")
    external = [u for u in re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
                if not u.startswith("https://focalis.cc")
                and not any(s in u for s in injected)]
    check("page makes no third-party requests", not external, ", ".join(external[:3]))

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text)
                if m.type == "error"
                and not host_noise(m.text, (m.location or {}).get("url", "")) else None)
        resp = page.goto(PAGE.as_uri() if LOCAL else BASE + "/audit/routes/", wait_until="load")
        check("browser loads the page", bool(resp and resp.ok))
        table_rows = page.eval_on_selector_all("table tbody tr", "els => els.length")
        check("table renders every measured route", table_rows >= len(ok_rows), str(table_rows))
        over = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
        check("no horizontal overflow at 390px", over <= 1, f"{over}px")
        browser.close()
        real_errors = [e for e in errors if not host_noise(e)]  # location-filtered on capture
        check("no console errors of our own", not real_errors, "; ".join(real_errors[:3]))

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

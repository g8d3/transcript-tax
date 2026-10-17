#!/usr/bin/env python3
"""Funnel link audit: every hop from a stranger to our inbox, resolved for real.

    python3 tests/funnel-links.py            # all seeds
    python3 tests/funnel-links.py <url> ...  # a subset

Why this exists: the pack is a chain of pages that point at each other (site root →
offer → self-serve preview → sample deliverable → paper → article → repo README → the
repos' own READMEs → mailto). A single dead hop silently costs a sale, and today one hop
had already drifted (repo `audit/index.html` was 5 hours stale). So: fetch each page, take
every href/src, resolve it, and for internal anchors (`page#id`) check that the id exists
in the target document.

Only our own hosts are status-checked (focalis.cc, github.com/g8d3, g8d3.github.io);
anything else is reported as `external` and not counted as a failure, because we do not
want this test failing when someone else's site has a bad day.
"""
from __future__ import annotations

import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from html.parser import HTMLParser
from urllib.parse import urljoin, urldefrag, urlparse

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/130 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
OURS = ("focalis.cc", "github.com", "g8d3.github.io", "raw.githubusercontent.com")
# Not links we wrote, and known to answer non-200 to an anonymous crawler:
#  * /cdn-cgi/l/email-protection — Cloudflare's email obfuscation of our own mailto
#  * github.com/{signup,login,join} — GitHub's own chrome, 403 without a session
SKIP = ("/cdn-cgi/l/email-protection", "github.com/signup", "github.com/login", "github.com/join")

SEEDS = [
    "https://focalis.cc/",
    "https://focalis.cc/about.html",
    "https://focalis.cc/contact.html",
    "https://focalis.cc/audit/",
    "https://focalis.cc/audit/preview/",
    "https://focalis.cc/audit/sample/",
    "https://focalis.cc/tps/",
    "https://focalis.cc/tps/article.html",
    "https://github.com/g8d3/transcript-tax",
    "https://github.com/g8d3/pi-web-tps-monitor",
]

fails: list[str] = []


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []
        self.ids: set[str] = set()
        self.assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "a" and "href" in a:
            self.hrefs.append(a["href"])
        if tag in ("img", "script", "link") and ("src" in a or "href" in a):
            self.assets.append(a.get("src") or a.get("href"))


def get(url: str, method: str = "GET") -> tuple[int, str]:
    req = urllib.request.Request(url, headers=UA, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read(400_000).decode("utf-8", "replace") if method == "GET" else ""
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return 0, str(e)[:80]


cache: dict[str, tuple[int, str]] = {}


def fetch(url: str) -> tuple[int, str]:
    if url not in cache:
        status, body = get(url)
        if status == 0 or status >= 500:      # one retry: GitHub throttles anonymous crawls
            time.sleep(2)
            status, body = get(url)
        cache[url] = (status, body)
    return cache[url]


def main() -> None:
    seeds = sys.argv[1:] or SEEDS
    pages: dict[str, Links] = {}
    for seed in seeds:
        status, body = fetch(seed)
        if status != 200:
            fails.append(f"{seed}: HTTP {status}")
            print(f"FAIL page {seed} -> {status}")
            continue
        p = Links(); p.feed(body)
        pages[seed] = p
        print(f"page  {seed} -> 200, {len(p.hrefs)} links, {len(p.assets)} assets, {len(p.ids)} ids")

    checked: set[str] = set()
    anchors_done: set[tuple[str, str]] = set()
    external: dict[str, int] = defaultdict(int)
    unverifiable: dict[str, int] = defaultdict(int)
    per_page: dict[str, list[str]] = defaultdict(list)
    for page, p in pages.items():
        for href in p.hrefs + p.assets:
            if href.startswith(("mailto:", "tel:", "javascript:", "data:")):
                continue
            target, frag = urldefrag(urljoin(page, href))
            host = urlparse(target).hostname or ""
            if host not in OURS or any(k in target for k in SKIP):
                checked.add(target)
                external[page] += 1
                continue
            # anchors are checked per (target, fragment): deduping on the URL alone would
            # only ever test the first anchor of a page (that is how a dead #method nav
            # link survived a whole release in R8).
            if frag and host in ("github.com", "g8d3.github.io"):
                # GitHub builds its section ids in client-side JS; a static fetch cannot
                # see them, so anchors there are counted as unverifiable, not as broken.
                unverifiable[page] += 1
                frag = ""
            if frag and (frag, target) not in anchors_done:
                anchors_done.add((frag, target))
                st, body = fetch(target)
                if st != 200:
                    fails.append(f"{page}: {href} -> HTTP {st or 'error'}")
                    per_page[page].append(f"{href} -> HTTP {st or 'error'}")
                else:
                    if target in pages:
                        id_set = pages[target].ids
                    else:
                        tmp = Links(); tmp.feed(body); id_set = tmp.ids
                    if frag in id_set:
                        per_page[page].append(f"{href} -> ok (anchor #{frag})")
                    else:
                        fails.append(f"{page}: anchor #{frag} not found in {target}")
                        per_page[page].append(f"{href} -> ANCHOR #{frag} MISSING")
            if target in checked:
                continue
            checked.add(target)
            st, body = fetch(target)
            if st != 200:
                fails.append(f"{page}: {href} -> HTTP {st}" if st else f"{page}: {href} -> {body}")
                per_page[page].append(f"{href} -> HTTP {st or 'error'}")

    for page in ("https://focalis.cc/audit/", "https://focalis.cc/audit/preview/",
                 "https://focalis.cc/audit/sample/"):
        if page in pages:
            has = any("mailto:" in h or "email-protection" in h for h in pages[page].hrefs)
            if not has:
                fails.append(f"{page}: no contact link")
            print(f"contact link on {page}: {'yes' if has else 'NO'}")

    print()
    for page, notes in per_page.items():
        if notes:
            print(f"{page}:")
            for n in notes:
                print("   ", n)
    for page, n in unverifiable.items():
        print(f"{page}: {n} anchor(s) not verifiable statically (host renders ids in JS)")
    for page, n in external.items():
        print(f"{page}: {n} external asset(s)/link(s) not status-checked (not ours)")
    print(f"\n{len(checked)} unique targets checked across {len(pages)} pages")
    if fails:
        print("\nFAILURES:")
        for f in fails:
            print(" -", f)
    print(f"\n{'FUNNEL OK' if not fails else f'{len(fails)} BROKEN'} — "
          f"{len(SEEDS)} seeds, {len(pages)} pages fetched")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()

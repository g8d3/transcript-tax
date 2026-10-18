#!/usr/bin/env python3
"""The offer must exist in exactly one place.

    python3 tests/offer-mirror.py

Why this test exists: `audit/index.html` in the paper's repository was documented as "the
offer page exactly as served", and it drifted **twice** — the last time by three offer
changes (the 7.7x route finding, the signed-NDA line, the Open Graph tags) that reached
the served page and not the committed copy, while that copy kept being served at
`/tps/audit/` and on GitHub Pages. A hand-copied price list is a page that will
eventually contradict the one being sold, so the repository keeps a **pointer** now, and
this test fails the day a copy comes back.

What it proves:
  1. the canonical offer/intake are live and still carry their price table / form,
  2. the in-repo paths (`/tps/audit/…`, GitHub Pages) are pointers: canonical link present,
     price table / form absent,
  3. the local clone, if one is named, keeps the same pointers (so the mistake is caught
     before it is pushed, not after).

Set TRANSCRIPT_TAX_REPO to check a specific clone; otherwise the first existing candidate
is used. No third-party imports: urllib only, so it runs anywhere.
"""
from __future__ import annotations

import os
import re
import sys
import urllib.request
from pathlib import Path

LIVE = "https://focalis.cc"
PAGES = "https://g8d3.github.io/transcript-tax"
HERE = Path(__file__).resolve().parent
# the clone to check is the one we are inside, or one named by the environment — never a
# machine path baked into the published repository
CANDIDATE_REPOS = tuple(p for p in (os.environ.get("TRANSCRIPT_TAX_REPO"), os.environ.get("REPO_ROOT"),
                                    str(HERE.parent)) if p)

# (name, url-or-path, required-substring, canonical-href, forbidden copy markers)
MIRRORS: list[tuple[str, str, str, str, list[str]]] = [
    ("live /tps/audit/", f"{LIVE}/tps/audit/",
     "https://focalis.cc/audit/", "https://focalis.cc/audit/", ["3,900", "$12,600"]),
    ("live /tps/audit/intake/", f"{LIVE}/tps/audit/intake/",
     "https://focalis.cc/audit/intake/", "https://focalis.cc/audit/intake/",
     ['id="intake"', "$3,900"]),
    ("gh-pages /audit/", f"{PAGES}/audit/",
     "https://focalis.cc/audit/", "https://focalis.cc/audit/", ["3,900", "$12,600"]),
    ("gh-pages /audit/intake/", f"{PAGES}/audit/intake/",
     "https://focalis.cc/audit/intake/", "https://focalis.cc/audit/intake/",
     ['id="intake"', "$3,900"]),
]

fails: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    if not ok:
        fails.append(name)


def get(target: str) -> tuple[int, str]:
    if target.startswith("http"):
        req = urllib.request.Request(target, headers={"User-Agent": "focalis-mirror-check"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, ""
        except Exception as e:  # network down must fail loudly, not pass
            return 0, f"{type(e).__name__}: {e}"
    p = Path(target)
    return (200, p.read_text()) if p.exists() else (404, "")


# 1. the canonical pages are alive and still the real thing
for canon, marker in ((f"{LIVE}/audit/", "3,900 USD"), (f"{LIVE}/audit/intake/", 'id="intake"')):
    code, body = get(canon)
    check(f"canonical {canon} is live", code == 200, f"HTTP {code}")
    check(f"canonical {canon} is still the offer itself", marker in body, f"marker {marker!r}")

# 2. every public copy of the path is a pointer, never a second offer
for name, target, required, canonical, forbidden in MIRRORS:
    code, body = get(target)
    check(f"{name} is reachable", code == 200, f"HTTP {code}")
    points = f'rel="canonical" href="{canonical}"' in body and required in body
    check(f"{name} points at the canonical page", points,
          "" if points else f"canonical href to {canonical} not found")
    hits = [m for m in forbidden if m in body]
    check(f"{name} is a pointer, not a copy (no offer content)", not hits,
          f"found {hits}" if hits else "")

# 3. the clone on disk already keeps the pointers (fail before the push, not after)
repo = os.environ.get("TRANSCRIPT_TAX_REPO") or next(
    (p for p in CANDIDATE_REPOS if Path(p, "audit", "index.html").exists()), None)
if repo:
    for rel, canonical, forbidden in (
            ("audit/index.html", "https://focalis.cc/audit/", ["3,900", "$12,600"]),
            ("audit/intake/index.html", "https://focalis.cc/audit/intake/", ['id="intake"', "$3,900"])):
        code, body = get(str(Path(repo) / rel))
        ok = code == 200 and f'rel="canonical" href="{canonical}"' in body
        check(f"clone {rel} kept the pointer", ok, "" if ok else f"HTTP {code}")
        hits = [m for m in forbidden if m in body]
        check(f"clone {rel} carries no offer copy", not hits, f"found {hits}" if hits else "")
    print(f"checked clone: {repo}")
else:
    print("no local clone found — set TRANSCRIPT_TAX_REPO to also fail before the push")

print(f"\n{len(fails)} failing check(s)")
sys.exit(1 if fails else 0)

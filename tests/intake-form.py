#!/usr/bin/env python3
"""Intake-form test: the money path, end to end, through a real browser.

    python3 tests/intake-form.py

It opens https://focalis.cc/audit/intake/ in Chrome, fills the three answers, submits, and then
checks that the lead actually arrived — the API's answer, the notification in the branded agent
inbox (the bcc copy), and the line in `logs/contact.jsonl` inside the site.

**It is not part of `tests/all.py` on purpose: every run sends a real email to the owner's
inbox.** The lead it sends is clearly labelled as an automated test.

Why this exists: until 2026-10-18 the contact API logged submissions and notified nobody (SMTP
was never configured), so a prospect who filled the form saw "we'll reply within 24h" and no
human ever saw it. This test is the gate on that leg.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://focalis.cc"
SENDER = "focalis@agentmail.to"
CONTACT_LOG = Path("/home/vuos/code/p4/sites/focalis.cc/logs/contact.jsonl")
fails: list[str] = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {extra}" if extra else ""))
    if not ok:
        fails.append(name)


def api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    key = os.environ.get("AGENTMAIL_API_KEY")
    if not key:
        raise SystemExit("AGENTMAIL_API_KEY is not set")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request("https://api.agentmail.to/v0" + path, data=data, method=method,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode() or "{}")


def main() -> int:
    token = f"intake-form-test {datetime.now(timezone.utc).strftime('%H:%M:%SZ')}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(BASE + "/audit/intake/", wait_until="load")

        # the abuse controls must reject *before* sending anything (no email on these paths).
        # Done from inside the browser: Cloudflare answers 403 code 1010 to bare urllib POSTs,
        # so a scripted request would test Cloudflare, not our validation.
        def post_from_page(payload: dict) -> tuple[int, str]:
            return tuple(page.evaluate(
                "async (p) => { const r = await fetch('/api/contact', {method:'POST', "
                "headers:{'Content-Type':'application/json'}, body: JSON.stringify(p)}); "
                "return [r.status, await r.text()]; }", payload))

        check("the form is on the page", page.locator("#intake").count() == 1)
        check("the honeypot is off-screen and unfocusable",
              page.eval_on_selector("#f-website",
                  "e => e.getBoundingClientRect().right < 0 && e.tabIndex === -1"))
        page.fill("#f-name", f"Automated test ({token})")
        page.fill("#f-email", "hello@focalis.cc")
        page.fill("#f-volume", "10 loops x 100 turns/day x 250 days (test payload)")
        page.fill("#f-cost", "test payload, no real fleet behind it")
        page.fill("#f-process", "test payload — warm service")
        page.click("#f-send")
        page.wait_for_function(
            "() => { const s = document.getElementById('f-status').textContent; "
            "return s && !s.startsWith('Sending'); }", timeout=30000)
        status = page.inner_text("#f-status")
        check("the page confirms receipt", "received" in status.lower(), status[:90])
        check("the form is cleared after sending", page.input_value("#f-name") == "")
        check("no console errors", not errors, "; ".join(errors[:2]))

        code, body = post_from_page({"name": "Honeypot probe", "email": "hello@focalis.cc",
                                     "message": "A bot filled the hidden field.",
                                     "website": "http://spam.example"})
        check("the honeypot is rejected without sending",
              code == 400 and "Spam" in body, f"{code} {body[:60]}")
        code, body = post_from_page({"name": "Validation probe", "email": "not-an-email",
                                     "message": "short"})
        check("bad input is rejected without sending", code == 400, f"{code} {body[:60]}")
        browser.close()

    # the lead must exist in all three places: the log, the API's own answer, the inbox copy
    line = None
    if CONTACT_LOG.exists():
        for raw in reversed(CONTACT_LOG.read_text().splitlines()):
            if token in raw:
                line = json.loads(raw)
                break
    check("the lead is written to logs/contact.jsonl", line is not None)
    if line:
        check("the log keeps the three answers", "1. Volume:" in line.get("message", ""))
        check("the log records the IP for abuse handling", bool(line.get("ip")))

    got = None
    for _ in range(8):
        time.sleep(3)
        for m in api(f"/inboxes/{SENDER}/messages?limit=5").get("messages", []):
            if token in (m.get("subject") or ""):
                got = m
                break
        if got:
            break
    check("the notification reaches the branded inbox", got is not None, token)
    if got:
        check("it is addressed to the human's inbox", "hello@focalis.cc" in (got.get("to") or []),
              str(got.get("to")))
        print(f"  delivered: {got.get('timestamp')} id={got.get('message_id')}")

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

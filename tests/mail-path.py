#!/usr/bin/env python3
"""Send-path check: can we actually reply to a prospect from a branded address?

    python3 tests/mail-path.py

It sends one message from `focalis@agentmail.to` to our own second inbox and asserts it
arrives, printing the sender and timestamp. It is **not** part of `tests/all.py` on
purpose: every run would send real mail. Run it after changing the inbox, the key or the
provider — the claim it protects ("a reply leaves from a branded address, not the owner's
personal Gmail") is otherwise unverifiable from the outside.

Why this matters: for weeks the pack said "write to hello@focalis.cc" while the reply leg
was undefined (inbound works via Cloudflare Email Routing; sending needed either a paid
plan or the owner's personal Gmail). The branded AgentMail inbox closes that gap.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

SENDER = "focalis@agentmail.to"          # branded sender (display name: "Focalis audit")
RECEIVER = "zcash_cat@agentmail.to"      # our own second inbox: readable via the API
API = "https://api.agentmail.to/v0"
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
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_error": f"http {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"}


def main() -> int:
    token = f"send-path-check {datetime.now(timezone.utc).strftime('%H:%M:%SZ')}"
    sent = api(f"/inboxes/{SENDER}/messages/send", "POST", {
        "to": RECEIVER,
        "subject": f"[test] {token}",
        "text": "Automated send-path check (tests/mail-path.py). Nothing to do; please ignore.",
    })
    check("the message is accepted by the provider", "message_id" in sent, sent.get("_error", ""))
    if "message_id" not in sent:
        print(f"\nFAILURES: {', '.join(fails)}")
        return 1

    got = None
    for _ in range(10):  # delivery is a few seconds; do not poll forever
        time.sleep(3)
        listing = api(f"/inboxes/{RECEIVER}/messages?limit=5")
        for m in listing.get("messages", []):
            if token in (m.get("subject") or ""):
                got = m
                break
        if got:
            break
    check("it arrives at our own inbox", got is not None, token)
    if got:
        check("it arrives from the branded sender, not a personal address",
              SENDER in (got.get("from") or ""), got.get("from", ""))
        check("the display name is the branded one", "Focalis audit" in (got.get("from") or ""),
              got.get("from", ""))
        print(f"  delivered: {got.get('timestamp')} id={got.get('message_id')}")

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

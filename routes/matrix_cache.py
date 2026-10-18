#!/usr/bin/env python3
"""Does the prefix cache actually engage on each route? Two identical calls, measured.

    python3 matrix_cache.py            # every route in routes.json["cache"]

The audit sells two levers the customer can actually pull: where the token enters (route)
and how much of it is re-sent every turn (context). This measures the second one per route:
send the same ~3k-token prompt twice in a row and read the provider's own
`prompt_tokens_details.cached_tokens` plus the wall delta. A miss here means "no hit
observed in this probe", not "caching is off" — one pair of calls cannot prove the latter,
and the page says so.
"""
from __future__ import annotations
import json, os, sys, time, urllib.error, urllib.request, uuid
from pathlib import Path

HERE = Path(__file__).parent
CFG = json.loads((HERE / "routes.json").read_text())
UA = {"User-Agent": "curl/8"}
FILLER = ("The audit measures wall-clock, model span, tool span and token spend per turn. " * 240)
PROMPT = FILLER + "\n\nReply with the single word PONG and nothing else."


def call(base, key, model, provider, timeout=120):
    body = json.dumps({"model": model, "stream": True, "max_tokens": 16,
                       "messages": [{"role": "user", "content": PROMPT}]}).encode()
    headers = {**UA, "Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    if provider == "opencode-go":
        headers["x-opencode-session"] = str(uuid.uuid4())
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body, headers=headers)
    t0 = time.time()
    ttft, usage = None, {}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    ev = json.loads(payload)
                except Exception:
                    continue
                if ev.get("usage"):
                    usage = ev["usage"]
                for ch in (ev.get("choices") or []):
                    d = ch.get("delta") or ch.get("message") or {}
                    if (d.get("content") or d.get("reasoning_content")) and ttft is None:
                        ttft = time.time() - t0
        total = time.time() - t0
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        return {"ok": True, "ttft_ms": None if ttft is None else round(ttft * 1000),
                "total_ms": round(total * 1000), "in_tokens": usage.get("prompt_tokens"),
                "cached_tokens": cached, "out_tokens": usage.get("completion_tokens")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"http {e.code}: {e.read().decode('utf-8', 'replace')[:120]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:140]}


def main() -> int:
    wanted = sys.argv[1:] or list(CFG.get("cache", {}))
    rows = []
    for anchor in wanted:
        for route in CFG["cache"][anchor]:
            provider, model = route["provider"], route["model"]
            base = os.environ.get(route["base_env"]) or CFG["defaults"].get(provider, "")
            key = os.environ.get(route["key_env"])
            if not base or not key:
                print(f"{anchor:22} {provider:12} SKIP")
                continue
            first = call(base, key, model, provider)
            time.sleep(1)
            second = call(base, key, model, provider)
            row = {"anchor": anchor, "provider": provider, "model": model,
                   "first": first, "second": second}
            if first.get("ok") and second.get("ok"):
                f_c, s_c = first.get("cached_tokens") or 0, second.get("cached_tokens") or 0
                row["state"] = "ok"
                row["hit"] = s_c > 0
                row["cached_share"] = round(s_c / second["in_tokens"], 3) if second.get("in_tokens") else None
                row["wall_delta_ms"] = second["total_ms"] - first["total_ms"]
                print(f"{anchor:22} {provider:12} ok  in={second['in_tokens']} cached={s_c} "
                      f"({row['cached_share']}) total {first['total_ms']}→{second['total_ms']} ms")
            else:
                row["state"] = "failed"
                row["error"] = first.get("error") or second.get("error")
                print(f"{anchor:22} {provider:12} FAILED {row['error']}")
            rows.append(row)
    path = HERE / "cache.json"
    kept = []
    if path.exists():
        kept = [r for r in json.loads(path.read_text()) if r["anchor"] not in set(wanted)]
    merged = kept + rows
    path.write_text(json.dumps(merged, indent=1))
    print(f"\nwrote cache.json ({len(merged)} routes: {len(kept)} kept + {len(rows)} measured)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

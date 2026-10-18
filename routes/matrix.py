#!/usr/bin/env python3
"""Provider matrix: the same model, several routes — price, first-token latency, total.

    python3 matrix.py            # all anchors in routes.json
    python3 matrix.py gpt-oss-120b

Why: the audit sells "your token costs depend on where it enters". This measures it.
Prices come from each provider's own /models metadata when it exposes one (OpenRouter,
Groq, Chutes do); when it does not, the row says so instead of guessing. Latency is
measured here, streaming, so first-token and total are separate numbers — the same
distinction the monitor makes (`preResponseMs` vs the model span).

No secret is printed: keys are read from the environment and never echoed.
"""
from __future__ import annotations
import json, os, statistics, sys, time, urllib.error, urllib.request, uuid
from pathlib import Path

HERE = Path(__file__).parent
CFG = json.loads((HERE / "routes.json").read_text())
MODELS = json.loads((HERE / "models.json").read_text())
REPS = int(os.environ.get("MATRIX_REPS", "2"))
PROMPT = "Reply with the single word PONG and nothing else."
UA = {"User-Agent": "curl/8"}


def price_of(provider: str, model: str):
    """$/M tokens (in, out, cache-read) from the provider's own metadata, or None."""
    meta = (MODELS.get(provider) or {}).get("priced") or {}
    p = meta.get(model)
    if not p:
        return None
    def num(v):
        if v is None:
            return None
        v = float(v)
        return round(v * 1e6, 6) if v < 1e-3 else round(v, 4)  # per-token vs per-M
    return (num(p.get("prompt")), num(p.get("completion")), num(p.get("input_cache_read")) if p.get("input_cache_read") else None)


def call(base: str, key: str, model: str, timeout=90, provider: str = ""):
    body = json.dumps({"model": model, "stream": True, "max_tokens": 16,
                       "messages": [{"role": "user", "content": PROMPT}]}).encode()
    headers = {**UA, "Content-Type": "application/json", "Authorization": f"Bearer {key}"}
    if provider == "opencode-go":
        # the pi gateway refuses a bare call: it routes by session, so give it one
        headers["x-opencode-session"] = str(uuid.uuid4())
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body, headers=headers)
    t0 = time.time()
    ttft = None
    text, usage = "", {}
    chunks = 0
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
                    chunks += 1
                    d = ch.get("delta") or ch.get("message") or {}
                    piece = d.get("content") or d.get("reasoning_content") or d.get("reasoning")
                    if piece:
                        if ttft is None:
                            ttft = time.time() - t0
                        text += piece
        total = time.time() - t0
        cached = ((usage.get("prompt_tokens_details") or {}).get("cached_tokens"))
        return {"ok": True, "streamed": chunks > 1,
                "ttft_ms": None if ttft is None else round(ttft * 1000),
                "total_ms": round(total * 1000), "out_tokens": usage.get("completion_tokens"),
                "in_tokens": usage.get("prompt_tokens"), "cached_tokens": cached,
                "text": text.strip()[:24]}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"http {e.code}: {e.read().decode('utf-8', 'replace')[:120]}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:140]}


def main() -> int:
    wanted = sys.argv[1:] or list(CFG["anchors"])
    rows = []
    for anchor in wanted:
        for route in CFG["anchors"][anchor]:
            provider, model = route["provider"], route["model"]
            base = os.environ.get(route["base_env"]) or CFG["defaults"].get(provider, "")
            key = os.environ.get(route["key_env"])
            if not base or not key:
                rows.append({"anchor": anchor, "provider": provider, "model": model,
                             "state": f"no {'base' if not base else 'key'}"})
                print(f"{anchor:22} {provider:12} SKIP (no {'base' if not base else 'key'})")
                continue
            price = price_of(provider, model)
            reps = [call(base, key, model, provider=provider) for _ in range(REPS)]
            good = [r for r in reps if r["ok"]]
            row = {"anchor": anchor, "provider": provider, "model": model, "price": price,
                   "state": "ok" if good else "failed",
                   "reps": reps,
                   "ttft_p50": round(statistics.median([r["ttft_ms"] for r in good if r["ttft_ms"]])) if any(r.get("ttft_ms") for r in good) else None,
                   "total_p50": round(statistics.median([r["total_ms"] for r in good])) if good else None,
                   "out_tokens": (good[0].get("out_tokens") if good else None),
                   "streamed": (good[0].get("streamed") if good else None),
                   "cached_tokens": (good[0].get("cached_tokens") if good else None),
                   "text": (good[0].get("text") if good else None),
                   "error": None if good else reps[0].get("error")}
            rows.append(row)
            print(f"{anchor:22} {provider:12} {row['state']:6} ttft={row['ttft_p50']}ms total={row['total_p50']}ms "
                  f"out={row['out_tokens']} streamed={row.get('streamed')} price/M={price} text={row['text']!r}" +
                  (f" ERR {row['error']}" if row["error"] else ""))
    # merge: re-measuring one anchor must not drop the others
    path = HERE / "matrix.json"
    kept = []
    if path.exists():
        kept = [r for r in json.loads(path.read_text()) if r["anchor"] not in set(wanted)]
    merged = kept + rows
    path.write_text(json.dumps(merged, indent=1))
    print(f"\nwrote matrix.json ({len(merged)} rows: {len(kept)} kept + {len(rows)} measured)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

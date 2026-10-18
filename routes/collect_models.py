#!/usr/bin/env python3
"""Download each provider's own model catalog and store the price metadata.

    python3 collect_models.py                 # refresh every provider below
    python3 collect_models.py venice          # refresh one

Why this exists: `matrix.py` reads every price from `models.json`, and every price on the
routes page, in the paper and in a paid deliverable traces back to a provider's **own**
`/models` metadata — never typed by hand (that is what keeps the route table honest when
prices rotate). `models.json` was collected by hand twice, so the recipe lived only in the
collector's memory: this is the recipe.

Price shapes differ by provider and none of them are guessed:
  * `pricing.prompt` / `.completion` / `.input_cache_read` — OpenRouter (per-token strings),
    Chutes and Groq (numbers). The value is copied verbatim; `matrix.price_of` normalises.
  * Venice nests it: `model_spec.pricing.{input,output,cache_input}.usd`, already $/M.

A provider whose catalog cannot be read keeps whatever is committed for it (state, ids and
prices) instead of being blanked — a 401 tonight must not delete last week's numbers.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "models.json"
UA = {"User-Agent": "curl/8"}

# provider -> (base env, default base, key env, catalog path, price reader name)
PROVIDERS: dict[str, tuple[str, str, str, str, str]] = {
    "openrouter": ("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "/models", "openai"),
    "chutes": ("CHUTES_BASE_URL", "https://llm.chutes.ai/v1", "CHUTES_API_KEY", "/models", "openai"),
    "groq": ("GROQ_BASE_URL", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "/models", "openai"),
    "venice": ("VENICE_BASE_URL", "https://api.venice.ai/api/v1", "VENICE_API_KEY", "/models?type=text", "venice"),
}
PRICE_KEYS = ("prompt", "completion", "input_cache_read")


def fetch(base: str, key: str, path: str):
    req = urllib.request.Request(base.rstrip("/") + path,
                                 headers={**UA, "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def as_list(doc) -> list[dict]:
    return doc.get("data") if isinstance(doc, dict) else doc


def openai_prices(model: dict) -> dict | None:
    pr = model.get("pricing") or {}
    kept = {k: pr[k] for k in PRICE_KEYS if pr.get(k) is not None}
    return kept or None


def venice_prices(model: dict) -> dict | None:
    pr = ((model.get("model_spec") or {}).get("pricing")) or {}
    def usd(part):
        v = (pr.get(part) or {}).get("usd")
        return v
    kept = {"prompt": usd("input"), "completion": usd("output"), "input_cache_read": usd("cache_input")}
    kept = {k: v for k, v in kept.items() if v is not None}
    return kept or None


READERS = {"openai": openai_prices, "venice": venice_prices}


def main() -> int:
    wanted = sys.argv[1:] or list(PROVIDERS)
    known = json.loads(OUT.read_text()) if OUT.exists() else {}
    for name in wanted:
        if name not in PROVIDERS:
            print(f"unknown provider {name!r}; known: {', '.join(PROVIDERS)}")
            return 2
        base_env, base_default, key_env, path, reader = PROVIDERS[name]
        base = os.environ.get(base_env) or base_default
        key = os.environ.get(key_env)
        if not key:
            print(f"{name:12} SKIP (no {key_env}) — committed entry kept")
            continue
        try:
            doc = fetch(base, key, path)
        except urllib.error.HTTPError as e:
            print(f"{name:12} http {e.code} — committed entry kept")
            continue
        except Exception as e:
            print(f"{name:12} {type(e).__name__}: {e} — committed entry kept")
            continue
        models = as_list(doc) or []
        if not models:
            print(f"{name:12} empty catalog — committed entry kept")
            continue
        ids = [m["id"] for m in models if m.get("id")]
        priced = {}
        for m in models:
            p = READERS[reader](m)
            if p:
                priced[m["id"]] = p
        known[name] = {"state": "ok", "n": len(ids), "ids": ids, "priced": priced}
        print(f"{name:12} {len(ids):4} models, {len(priced):4} with a price")
    OUT.write_text(json.dumps(known, indent=1))
    print(f"\nwrote {OUT.name}: {len(known)} providers, "
          f"{sum(len(v.get('priced', {})) for v in known.values())} priced models")
    return 0


if __name__ == "__main__":
    sys.exit(main())

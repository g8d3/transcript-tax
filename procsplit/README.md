# procsplit — where a turn's wall clock actually goes, measured from outside the harness

Raw data and the reproducer for the decomposition the paper's §5.4, the front page and a paid
deliverable all cite:

| segment | 2026-10-18, warm cache | 2026-10-18, cold cache | 2026-10-17 (§5.4 as published) |
|---|---|---|---|
| boot — process start → first NDJSON line | **372 ms** | **940 ms** | 929 ms |
| turn_start → assistant `message_start` | **1554 ms** | 1520 ms | 1451 ms |
| first text → `message_end` (stream) | **3 ms** | 7 ms | 2 ms |
| total process wall | 1974 ms | 2598 ms | 2453 ms |

Files: `procsplit-2026-10-18-warm.json` (5 reps) and `procsplit-2026-10-18-cold.json` (3 reps).
Every number above is the median of the `segments_ms` in those files, rounded
to the nearest millisecond (the files keep the exact value, e.g. a 371.5 ms boot) — recompute with
`tests/procsplit-claims.py`, which also fails if a page quotes a different value.

## Why boot has two numbers

The 929 ms published on 2026-10-17 was measured before the extension that loads on startup was
changed. **Two HTTPS catalog fetches were running inside that boot window**; they are now behind a
6-hour cache (`PI_OPENCODE_SYNC_TTL_MS`), so the same command on the same machine measures
372 ms. Forcing the fetches back on (`--cold`, which sets that env var to `0`) reproduces the old
number — 940 ms — which is the proof that the difference is those two calls and not a change of
machine, model or prompt.

That matters beyond the paper: the boot is the one lever this pack sells as *removable*, and it is
2.5x smaller than the number we had been quoting. Warm is the common case (a loop that spawns a
process per turn keeps the cache fresh); cold is the first call after six idle hours.

## Reproduce

```bash
python3 procsplit/measure.py --reps 5 --out /tmp/warm.json
python3 procsplit/measure.py --reps 3 --cold --out /tmp/cold.json
```

Needs `pi` on `PATH` and a provider key for the chosen route (`--provider`, `--model`). It passes
`--workdir` through to the subprocess so a warm session is a real warm session; without it every
run starts in a fresh temp directory. Nothing is uploaded anywhere: the numbers are read off the
arrival times of the subprocess's own stdout lines.

## Limits (stated, not hidden)

- One machine, one route (opencode-go), one prompt, 3–5 reps. The spread of the provider roundtrip
  across reps is wide by nature (1183–7518 ms cold, one rep hit a provider stall); the medians are
  what we quote, and the per-rep marks are in the JSON so the tail is not lost.
- The roundtrip is a *client-side* window: it contains DNS, TLS, queueing and the provider's
  prefill. This measurement cannot split dispatch from prefill, and we say so instead of guessing.
- Boot varies with what a user's own extensions do — that is exactly why the two cache states are
  published as a pair rather than as one number.

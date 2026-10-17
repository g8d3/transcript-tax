# Claims audit — every number on our offer pages, and where it comes from

## Published URLs (2026-10-17 15:5xZ)

| what | where |
|---|---|
| paper (hosted) | https://focalis.cc/tps/ (+ https://g8d3.github.io/transcript-tax/) |
| repo (code + CSV + figures, MIT / CC BY 4.0) | https://github.com/g8d3/transcript-tax |
| offer page (prices, objections, contact) | https://focalis.cc/audit/ |
| contact (working: Cloudflare Email Routing rule) | hola@focalis.cc → owner's inbox |

Run 2026-10-17 by re-computing from `bench.csv` (via `analyze.py`) and from the fleet
window published in [`fleet/`](fleet/). Method: no number is allowed in the money-facing
copy unless it is (a) recomputed by a script in this repository, (b) explicitly labelled
as a prior result with its n, or (c) explicitly labelled as an assumption.

**How to read the `where` column:** `landing N` = section N of the offer page at
<https://focalis.cc/audit/>; `report §N` = section N of `REPORT.md`; `intake` = the intake
page at <https://focalis.cc/audit/intake/>; file:line references are to the monitor's
source at <https://github.com/g8d3/pi-web-tps-monitor>.

Status legend: **OK** = verified against data · **PRIOR** = from the earlier 8-session
series, not in this dataset · **ASSUMPTION** = a parameter, not a measurement ·
**FIXED** = was wrong in the draft, corrected in place.

| claim | where | source | status |
|---|---|---|---|
| no-op turn median 2.4–3.4 s | landing 1, thread 1 | 6 cell medians: 2.42, 2.94, 3.05, 3.26, 3.35, 3.36 | **OK** |
| model span for a one-word reply is milliseconds | landing 1, thread 2 | pi rows: llm p50 2 ms | **OK** |
| boot 929 ms + pre-response 1451 ms + stream 2 ms = 2453 ms per one-word turn | landing 1 | external NDJSON-arrival measurement, 5 reps (`REPORT.md` §5.4) | **OK** |
| "cannot split pre-response into dispatch vs provider" | landing 1, objections | nothing exposed to an external observer separates them; `provider_stream_event` fires with the response | **OK** |
| "the rest is provider plus harness, we cannot split it" | landing 1, thread 2 | report §5 | **OK** |
| size ≈ 1 s fixed + 0.5 ms/KB | landing 1, thread 3 | **coefficient mis-stated 10x** (its own table implies ~5-6 ms/KB at 100-230 KB); fresh rebuild attempt failed (452 KB ingest → 108 KB session) | **FIXED** (report §8; copy now quotes ranges, not a slope) |
| "startup scans ~200 MB of sessions" / "fix the startup scan" | report §1.6, §3 rule 4 | `pi --version` is 244-248 ms from a 298 MB session dir and 242-253 ms from a near-empty one; session load 246 ms | **FIXED** (report §7; cut list no longer sells it) |
| ~5 s/turn at megabyte scale | landing 1, thread 3 | same series; report notes compaction likely engaged | **PRIOR** |
| cache state predicts wall / "miss rate 5 in 10" | landing 1, thread 4, objections | **not supported**: cache_tok 9216 → walls 16.55, 2.94, 3.18; 9344 → 20.00, 6.38, 2.83; only 1 of 4 slow runs reported 0 cached | **FIXED** (report §6; copy now reports the negative result) |
| 1,000 no-op turns ≈ 50 min | landing 1, thread 5 | median floor 3.14 s × 1000 = 52.3 min | **OK** |
| 10 loops × 100 turns/day = ~8 wall-hours/day | landing 1 | wrong by ~9x: 1000 × 3.14 s = 52 min | **FIXED** (now ~52 min no-op, ~2.4 h real work) |
| 500 live turns: 8.7 s wall, 34% model / 29% tools / 37% unaccounted | landing 1, thread 5 | fleet-scan, 500 rows, own monitor logs | **OK** |
| unaccounted floor p50 1.5–2.5 s per model, does not track the model | landing 1 | per-model p50 1470/2129/2524 ms vs llm p50 1 ms–9.1 s | **OK** |
| p90 3.4–5.9 s, worst turns 85 s (128 s on a broken provider) | landing 1 | fleet-scan by-model table | **OK** |
| 4.4% of turns produced nothing | landing 1, objections | 22/500 (21 error, 1 aborted) | **OK** |
| waste has no dollar figure | landing 1 | all 21 errors ran on an unpriced model | **OK** |
| audit pays for itself above ~$19k/yr token spend | pricing, landing 3, objections | `roi.py --sweep` at 35% input cut, 70% cache hit | **DERIVED** (from assumptions) |
| payback table (769 / 90 / 18 / 38 working days) | pricing, landing 3 | `roi.py --sweep` | **DERIVED** |
| 3.0 s floor, 5 s miss penalty, 30% miss rate | roi.py defaults | assumptions; §6 says the miss penalty is unconfirmed | **ASSUMPTION** (labelled in output) |
| "20–50% off steady-state wall" target with refund | pricing 3, landing 2 | target, not a measurement | **ASSUMPTION** (labelled as target) |
| boot 929 ms per turn is removable by keeping a process warm | landing 1, pricing 3 | measured boot 929 ms (911-984); `roi.py --warm` removes it from the model | **OK** |
| tool ships `preResponseMs` (turn start → provider first token) as a turn-row field | landing ("we ship the instrument") | capability, verified in shipped code: field `protocol.ts:59`, Turns-view `Pre` column `index.ts:353`, `/tps turns` `pre` segment `companion.ts:346`; driver test writes `preResponseMs` correctly | **OK** as a code capability — see next row for what is NOT yet true |
| "a live column in your panel" | landing ("we ship the instrument") | **VERIFIED TRUE 2026-10-17 10:45Z** (was FIXED-up as untrue at 08:4xZ): the daemon now serves the exact local build — `/pi-web-plugins/tps-monitor/dist/browser/index.js` sha256 `bb1bd256…` = local `dist/` byte for byte, `/api/plugins` reports `staleRevision:false` / `restartRequired:false`, the bundle contains `preResponseMs`/`wastedCost`/`decodeTps`/`fmtPartialCost`, and live rows in `code/p4/.pi-web/tps-turns.jsonl` carry `preResponseMs` (83/500 rows since the fix; p50 2929 ms). The old blocker was a sessiond restart, which happened at ~09:50 local | **OK** (re-verified against the SERVED artifact, not just the source) |
| "we ship the instrument" capability row | landing | field `protocol.ts:59`, Turns-view `Pre` column `index.ts:353`, `/tps turns` `pre` segment `companion.ts:346`; driver test writes `preResponseMs` correctly | **OK** |
| tool flags turns that burn budget and produce nothing | landing ("we ship the instrument") | capability: `isWastedTurn` / `turnWaste`, Fleet **Waste** column, `/tps cost` and `/tps fleet` | **OK** (capability) |
| tool refuses to print a fabricated rate for a one-word reply (reads "–") | landing ("we ship the instrument") | capability: `rate-floor.test.mjs`; a window under `tuning.minStreamMs` (`companion.ts:23`, gate at `:511`) stores `streamed:false`, and the panel renders that as "–" / "replayed" (`index.ts:304`) | **OK** (capability) |
| 208 wall-hours/year for 10 loops × 100 turns | objections | 3.14 s × 250,000 = 218 h; stated as 208 from the 3.0 s round floor | **OK** (round) |

## Corrections 2026-10-17 20:3xZ  — the "no analytics" class of claim

| claim | where | what the check found | status |
|---|---|---|---|
| "No analytics, no fonts, no requests after the page loads" | preview banner | **false on the hosted copy.** With a browser UA + `Accept: text/html`, Cloudflare injects `static.cloudflareinsights.com/beacon.min.js` (Web Analytics) and `cdn-cgi/scripts/…/email-decode.min.js` into **every** HTML page on focalis.cc — verified with curl on /audit/, /audit/preview/, /audit/sample/ and /tps/article.html. The file we build really does make no request of its own; the host adds two. | **FIXED** in all six places in one pass (preview banner + its limits list, sample footer, landing footer, landing calculator paragraph, landing paper line, article footer) — and both browser tests now **fail on any third-party request other than the host's two**, so the next injection cannot hide. |
| "the page has no external requests" | article footer, `/tps/article.html` + repo | same injection, unqualified sentence | **FIXED**, regenerated, committed and pushed (`ea8b320`) |
| "`audit/index.html` is the offer page exactly as served" | repo README invariant | the committed copy had **drifted** since 11:07Z: no preview link, no sample link, three paper/repo URLs as plain text, old footer | **FIXED**, re-synced + pushed (`1aeeb78`) |

Why this class keeps coming back: the claim is about the artifact we control (the file on
disk), while the thing a prospect inspects is the artifact the host delivers. Any
"no X" sentence must name which of the two it is talking about, or it is false on one of
them.

## Additions 2026-10-17 20:5xZ  — the intake page and the funnel

| claim | where | source | status |
|---|---|---|---|
| "the three questions we send are the same ones we publish" | landing, "Next step" | **nothing was published** when the sentence was written | **FIXED**: the intake is now a page (https://focalis.cc/audit/intake/) and the landing links it in the same sentence |
| intake figures: $290 / $1,400 / $3,900 / $490 per month, delivery 5 / 10 / 20 business days | intake §3 | `pricing.md` (same tiers and windows, checked line by line) | **OK** |
| "the rows carry no prompt text, no tool output" | intake §2 | `TpsTurn` (protocol.ts): ts, sessionId, model, turnIndex, durations, tokens, outcome, tool **names and durations** — no message text and no tool output | **OK** |
| 929 ms boot = 65 wall-hours/year at 10 loops × 100 turns/day | intake §1, landing, preview limits | `roi.compute().boot_hours` = 64.58 h (`roi.py`) | **OK** |
| $19k/year token-spend line, 35% input cut, "we would say no" | intake §4 | `roi.py --sweep` + `pricing.md` | **OK** |
| free self-serve preview on your own log | landing step 1, plugin README, intake | page built and parity-tested (`tests/preview-parity.py`, 22 checks against the deployed URL) | **OK** |

## Rules this audit leaves behind

1. A number in the copy must be recomputable by a script in the pack (`roi.py`,
   `analyze.py`) or labelled PRIOR/ASSUMPTION in the sentence itself.
2. Negative results get published too: the cache claim is now a post, not a silence.
3. When a claim is retracted, every place it appears gets fixed in the same pass —
   landing, thread, objections, calculator notes, report. Grep for the phrase, not the file.

## What this file is for

It exists so that a reader does not have to trust us: every number on the offer page has a
source and a status here, corrections are kept in place rather than deleted, and the rules
at the end are the ones the next edit is held to. If a claim on our pages is not in this
table, treat it as unverified and tell us.

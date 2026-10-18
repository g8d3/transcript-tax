# Claims audit — every number on our offer pages, and where it comes from

## Published URLs (2026-10-17 15:5xZ)

| what | where |
|---|---|
| front page (landing; the 3D game it replaced is still at /world/) | https://focalis.cc/ |
| paper (hosted) | https://focalis.cc/tps/ (+ https://g8d3.github.io/transcript-tax/) |
| repo (code + CSV + figures, MIT / CC BY 4.0) | https://github.com/g8d3/transcript-tax |
| offer page (prices, objections, contact) | https://focalis.cc/audit/ |
| seller pages (who sells, terms, privacy, refunds) | https://focalis.cc/company · /terms · /privacy · /refunds · /contact |
| route dispersion (same model, several providers) | https://focalis.cc/audit/routes/ (+ `routes/matrix.json`) |
| contact (working: Cloudflare Email Routing rule) | hello@focalis.cc → owner's inbox (hola@ and contact@ route to the same inbox) |
| reply leg (working: verified by `tests/mail-path.py`) | outbound from the branded inbox `focalis@agentmail.to` (display name "Focalis audit"), sent through AgentMail/Amazon SES. Sending *as* focalis.cc still needs a paid mail plan; we do not reply from a personal address |

Run 2026-10-17 by re-computing from `bench.csv` (via `analyze.py`) and from the fleet
window published in [`fleet/`](fleet/). Method: no number is allowed in the money-facing
copy unless it is (a) recomputed by a script in this repository, (b) explicitly labelled
as a prior result with its n, or (c) explicitly labelled as an assumption.

**How to read the `where` column:** `landing N` = section N of the offer page at
<https://focalis.cc/audit/>; `homepage` = the front page at <https://focalis.cc/> (a landing
since 2026-10-18 03:5xZ, previously a 3D game); `report §N` = section N of `REPORT.md`; `intake` = the intake
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
| 500 live turns: 8.7 s wall, 34% model / 29% tools / 37% unaccounted | landing 1, homepage, thread 5 | fleet-scan, 500 rows, own monitor logs. **"37% unaccounted" is a pre-v23 reading**: with `preResponseMs` measured (report §9, same quantity on a published window) it is 52% *provider round-trip* and the residual is p50 4 ms — the paper says a dashboard still reporting 37% today is reporting its own blind spot. The homepage card now says this; the number is kept because it is what the older method produced | **OK, with the §9 reading stated wherever it appears** |
| unaccounted floor p50 1.5–2.5 s per model, does not track the model | landing 1 | per-model p50 1470/2129/2524 ms vs llm p50 1 ms–9.1 s (pre-v23 reading: that floor is the provider round-trip, §9) | **OK** |
| p90 3.4–5.9 s, worst turns 85 s (128 s on a broken provider) | landing 1 | fleet-scan by-model table; the p90 here is the pre-v23 "unaccounted", so it is provider wait (§9). The homepage no longer quotes it as a residual | **OK** |
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

## Additions 2026-10-17 00:0xZ — the delivered artifacts and their public examples

| claim | where | source | status |
|---|---|---|---|
| `/audit/sample/` is "a filled example" of the breakdown a client receives | sample page | generated by `audit_report.py --banner sample` from our published one-word-turn numbers; the volume/price example is stated as such on the page | **OK** |
| `/audit/sample/{cache-report,size-curve,cuts,budget}.html` are filled examples of the Tier 2 deliverables | sample pages | same engine, run on **our own window** (500 turns + 500 message samples, 2026-10-17); each page says it is our data, not a client result | **OK** (with the caveat below) |
| the message-sample window behind the cache/size examples | not published | that log rotates like the turn log; the **turn** window behind §1.3/§9 *is* published (`fleet/`), the message-sample window is not. Numbers on those two example pages are ours and can be re-derived by anyone running the monitor, but not re-checked against a file we ship | **CAVEAT** (stated here on purpose) |
| "a regression check script you keep" (Tier 2/3) | pricing, deliverable, `audit-offer.md` | `regression_gate.py` exists, is delivered in the folder, and is tested failing at +50% wall / 10% waste and never re-baselining itself | **OK** |
| the six deliverables listed in `audit-offer.md` | audit-offer | `audit_report.py --outdir` writes exactly those six plus the gate and an index | **OK** |
| "~100 KB default compaction gate" | pricing Tier 2 | heuristic, now labelled as one in the same sentence as the §8 retraction | **FIXED** |
| the seller is Focalis S.A.S. (Bogotá) and the audit is sold on this site | landing "Who we are", /company, /terms §2 | the landing used to say "Nova Radar — a risk radar for Solana … real trades carrying on-chain signatures", a different seller identity; /terms and /refund said focalis.cc "does not itself sell" and "does not charge". All four rewritten 2026-10-18 (`tests/company-pages.py` asserts it) | **FIXED** |
| the 4 prices on /company are the published prices | /company | `tests/company-pages.py` parses `pricing.md` and asserts each figure appears; one source, no drift | **OK** |
| payment is collected by a merchant of record and card data never reaches us | /company, /terms §2, /privacy §4, landing "Next step", homepage | the pages now say it in the conditional ("will be handled … once it is switched on", "once checkout is enabled", "when you pay by card") and the offer page names the current path instead ("card checkout is not live yet — the merchant-of-record application is in progress — so today we invoice directly: bank transfer or stablecoin"). Dodo compliance replied 2026-10-18 01:21Z that Colombia is eligible and asked for the product information form, so the flow is still the design we are applying for, not a running system | **OK (conditional wording, verified 2026-10-18)** |
| refund promises on /refunds match the offer | /refunds §2 vs pricing Tier 3 | "implementation half is refunded" if the 20–50% target is missed on the re-run, "no lever → the implementation half is never charged" (pricing.md), "cancel any month" (retainer) | **OK** |
| the same model costs up to 20.5x more on one route than another | /audit/routes/ | recomputed by `tests/routes-page.py` from `routes/matrix.json`: qwen3.8-27b $0.039/M (chutes) vs $0.80/M (groq) input, from each provider's own `/models` metadata | **OK** |
| the cheapest route is not the fastest | /audit/routes/ | same source: qwen3.8-27b first token 318 ms (groq) vs 1808 ms (dashscope), 5.7x; deepseek-v4.1-flash 588 ms (openrouter) vs 1404 ms (opencode-go), 2.4x | **OK** |
| two routes "exist but cannot answer" | /audit/routes/ | measured: aihubmix `403 account balance is insufficient`, cerebras `402 payment required`; published as unavailable rather than as options | **OK** |
| `opencode-go` is an OpenAI-compatible endpoint | not claimed any more | a key-only call returns `400 MissingSessionID … x-opencode-session`: it routes by harness session, so a session id is part of the route | **FIXED** (documented on the routes page) |
| the prefix cache engages per route | /audit/routes/ (cache table) | two identical ~4k-token prompts per route: openrouter reported 4096/4122 cached (99.4%), chutes 93.8%, deepseek direct 98.1%, **opencode-go reported 0** and openrouter+gpt-oss-120b 1.2%; the page states that a miss is not proof that caching is off | **OK** (with that caveat printed) |
| "we reply within 24h" (the contact form's own promise) | /contact, /audit/intake/ | until 2026-10-18 the form wrote the lead to `logs/contact.jsonl` and notified nobody (SMTP was never configured). Now: notification email to hello@focalis.cc via the branded AgentMail inbox, bcc kept for agents, and `tests/intake-form.py` proves the whole chain in a real browser | **FIXED** |
| the intake form's abuse limits | not on the page | 5/minute, 10/hour, 20/day per IP, global 100 notifications/day; verified in the container (`_contact_rate_ok` returns False at each boundary) | **OK** |

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

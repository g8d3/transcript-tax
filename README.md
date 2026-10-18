# Transcript Tax 2026 — data and reproduction

Working paper: what a "trivial" agent turn costs, measured on one machine over one
night. 65 runs, 3 harnesses, ~8 cents of provider spend.

**Status: published 2026-10-17.** The paper is served at
<https://focalis.cc/tps/> (and via GitHub Pages at
<https://g8d3.github.io/transcript-tax/>). Nothing else from our sales pack has been
posted on social media.

## Files

| file | what it is |
|---|---|
| `REPORT.md` | the paper: claims, evidence, caveats, correction (§5) |
| `bench.csv` | the dataset — 65 rows, one per measured turn |
| `PROTOCOL.md` | exact setup, prompts and retry rules used to produce it |
| `analyze.py` | recomputes every table in `REPORT.md` from `bench.csv`, regenerates the figures |
| `tools/roi.py` | the calculator behind the audit offer (no dependencies): `python3 tools/roi.py --sweep` shows which fleets the audit pays for, and the page at <https://focalis.cc/audit/> runs the same arithmetic in your browser |
| `tools/roi.js` | that same arithmetic for the browser, inlined into `audit/index.html` by the pack's build script |
| `tests/roi-parity.mjs` | runs `roi.js` and `tools/roi.py` over a 63-case grid and fails if any number, displayed string or pay/no verdict differs (`node tests/roi-parity.mjs`) |
| `tests/roi-browser.py` | drives the real page in Chrome (playwright) and compares every rendered figure against `tools/roi.py`, including after changing the inputs |
| `audit/index.html` | a **pointer** to the offer page at <https://focalis.cc/audit/> — deliberately not a copy. A byte-copy lived here and drifted three times (route finding, NDA line, Open Graph tags); `tests/offer-mirror.py` fails if a price list is committed here again |
| `audit/intake/index.html` | a **pointer** to the intake at <https://focalis.cc/audit/intake/>: the three questions we ask, what to attach, tiers, when we say no — and the form itself, which is only wired to the API where it is served |
| `routes/` | **the route-dispersion study** published at <https://focalis.cc/audit/routes/>: `collect_models.py` downloads each provider's own `/models` metadata (the recipe that produces `models.json`; it reads OpenRouter/Chutes/Groq `pricing.*` and Venice's nested `model_spec.pricing.*.usd`, and leaves a provider's committed numbers alone if its catalog cannot be read); `matrix.py` calls the same model on every provider we hold a key for and measures price, first token and total; the cache probe (`matrix_cache.py`) writes `cache.json`; `render_matrix.py` writes `MATRIX.md` from the JSONs and `build_routes.py` publishes it; `emit_routes_snapshot.py` copies the measured prices into the delivery engine (`audit_report.ROUTES`) so that hand-typed snapshot cannot drift. Raw `matrix.json`, `cache.json` and `models.json` are included so every figure on the page can be recomputed |
| `procsplit/` | **the per-turn decomposition, measured from outside the harness** (`measure.py` runs `pi -p --mode json` as a subprocess and timestamps every NDJSON line, so boot / provider roundtrip / stream are separate numbers with no hook inside pi) plus the raw runs: 929 ms of boot on 2026-10-17, then 371 ms warm / 940 ms cold on 2026-10-18 after the two startup catalog fetches were cached for 6 h. This is the artifact behind §5.4, the front page's "process boot" figure and every paid deliverable's boot line |
| `tests/company-pages.py` | the seller pages a payment provider reads (`/company`, `/terms`, `/privacy`, `/refunds`, `/contact`): the published prices are checked against the offer's own `pricing.md`, the private forwarding address is checked to be absent from every public asset, and every internal link on those pages must resolve |
| `tests/routes-page.py` | recomputes the route matrix's own claims (price ratios, latency ratios, cache-hit count) from `routes/*.json` and fails if the published page drifts from the data |
| `tests/matrix-prices.py` | every price in the published route matrix is recomputed from the providers' **own** current catalogs with the measurer's own function (`routes/matrix.py`, imported) and the test fails naming the row when one has rotated — the loop that `collect_models.py` cannot close by itself, since it does not run on its own |
| `tests/paper-matrix.py` | the paper's §10 table, and the two counts its prose states, are checked against the generated `routes/MATRIX.md` |
| `tests/bench-claims.py` | recomputes the 2.4–3.4 s no-op floor, the 65 runs and the three harnesses from the published `bench.csv` and fails if the front door, the offer or the paper's claim 1 drift from it |
| `tests/fleet-window.py` | recomputes the statistics of the **published** fleet window (`fleet/fleet-turns-*.jsonl`) and fails if the homepage, the offer or the sample deliverable quote a different fleet window — which is exactly what happened once the live log rotated |
| `tests/offer-mirror.py` | the offer exists once: `/tps/audit/` and GitHub Pages must be canonical pointers to `focalis.cc/audit/`, never a committed copy that can drift |
| `tests/intake-form.py` | fills the intake form in a real browser and checks the lead reached the log *and* the notification email; also checks the honeypot and input validation are rejected before anything is sent. **Sends one real email per run**, so it is run on demand, not in the suite |
| `tests/mail-path.py` | proves the reply leg: a message leaves from the branded inbox and arrives, so we never have to answer a prospect from a personal address. Sends one real email per run |
| `CLAIMS.md` | the claims audit of our own offer pages: every number, its source, its status (including the four mechanisms we retracted and the two claims we had to qualify) |
| `tests/funnel-links.py` | resolves every hop from the site root to the inbox (11 pages, ~320 targets) and fails on a dead link, a dead in-page anchor or a missing contact link |
| `fig1..fig4.png` | figures, generated by `analyze.py` |
| `fleet/publish_fleet.py` | exports a window of our own fleet's logs and re-analyses it under both methods. `export` (turns) and `export-history` (message samples) replace `sessionId` with an opaque label and **drop `sessionName`** — the private label of a session, which the turn log started carrying on 2026-10-18 — and nothing else — `python3 fleet/publish_fleet.py analyze fleet/fleet-turns-2026-10-17.jsonl` |
| `fleet/fleet-turns-2026-10-17.jsonl` | the window analysed in §9: 500 turns, no prompt text, no session ids |
| `fleet/fleet-turns-2026-10-18.jsonl` + `fleet/fleet-history-2026-10-18.jsonl` + `fleet/example-answers.json` | the three published inputs of the four example deliverables at <https://focalis.cc/audit/sample/>: turn window, message-sample window and the answers used. Running the delivery engine on exactly these reproduces the served pages byte for byte (checked by `tests/sample-repro.py`), so the example a prospect reads is a function of files they can download |

## Reproduce

```bash
python3 analyze.py            # tables + figures (figures need matplotlib)
python3 analyze.py --tables   # tables only, stdlib only
```

`analyze.py` is the source of truth for every number: if a printed value disagrees
with `REPORT.md`, the CSV and the script win. The offer page's calculator is held to
the same rule: `tests/roi-parity.mjs` compares it field-by-field against
`tools/roi.py` (945 checks over 63 input combinations), including the formatted
strings the page shows — so the page cannot print a payback the script disagrees with. Known rounding slip in the first
draft: the zero-S median printed as 3.06 is 3.055 (10 runs, mean of the two middle
values) — a 0.01 s difference, corrected in this repo.

## Dataset columns

`harness,size,run,wall_s,llm_ms,total_ms,unacc_ms,in_tok,cache_tok,out_tok,notes`

- `run=0` is the ingest turn; `run=1..10` are the no-op PONG turns.
- `pi` rows carry `llm/total/unacc` from `.pi-web/tps-turns.jsonl`; `zero` rows carry
  provider usage only; `pirust` rows are wall-only by design (no instrumentation).
- `size=S|L` is the ingest *attempt* (100 KB / 2 MB), not the resulting context: the
  2 MB ladder did not stick (see `REPORT.md` §1.4). Do not fit wall-vs-size on it.
- `notes` records attempt number, cost where known, and the anomaly.

## Read this before quoting a number

0. **`CLAIMS.md` is the audit trail for everything we sell.** Every figure on
   <https://focalis.cc/audit/>, its source and its status, with corrections left in place.
   If a claim is not in that table, treat it as unverified and tell us.

1. **§1.2 is corrected by §5.** The LLM-span clock (`message_start` →
   `message_end`) does not reliably cover the provider roundtrip: for short
   single-chunk replies it collapses to ~0 ms. "The LLM is free, unaccounted
   dominates" is partly a measurement artifact. The wall floor is measured outside
   the harness and stands.
2. **TL;DR 4 and §1.3 are retracted by §6.** Cache state did not separate the slow
   runs from the fast ones: the same `cache_tok` value covers a 16.6 s run and two
   ~3 s runs. Do not quote "cache hits dominate wall time" or "miss rate 5 in 10".
2b. **§1.6's startup scan is retracted by §7** (startup costs the same from a 298 MB
   session store and a near-empty one), and **TL;DR 2's size coefficient is retracted
   by §8** (it was 10x off its own table, and a fresh rebuild attempt failed).
3. **n is small** (10 pongs per cell, one machine, one night). Jitter is ~1 s.
   Nothing here resolves sub-second differences between harnesses.
4. **Providers differ per cell** (pi used `deepseek-v4.1-flash`, pirust used
   `deepseek-chat`, zero used its own `medium` path). Cross-harness gaps are
   confounded; within-harness patterns are the robust result.

## Hire us (this is the pitch; the rest of the repo is not)

We run agent fleets ourselves and we measure this tax on them. If your fleet's bill
scales with turns x context and nobody can explain the line item:

- **The audit**: we instrument your loops, measure where the wall-clock and the
tokens go per turn (boot / pre-response / stream / tools), and hand you a breakdown
page plus a ranked cut list derived from *your* profile. Read-only first.
- What we do **not** sell: cache discipline, startup-scan scoping, a size
coefficient. All three failed to reproduce in our data — see the retractions above.
- The offer page, prices and the arguments against buying are here:
<https://focalis.cc/audit/>. Run `roi.py --sweep` there first; if the numbers say no,
we will too.
- Contact: **hola@focalis.cc**.

## License

`LICENSE` holds both: code (`analyze.py`, `build_article.py`) under MIT, text,
figures and `bench.csv` under CC BY 4.0. When citing, cite the revision — sections 5-8
are corrections, and a claim retracted there should not be quoted against the paper.

# Measurement protocol — the transcript-tax series (n=10 per cell)

This is the protocol behind `bench.csv`, kept as it was run so the numbers can be
reproduced or contradicted. Paths below are generic: the series ran in a throwaway
directory per cell (`<root>/<cell>/`) on one machine, with the file sizes given.

Cells: `piS`, `piL` (pi-TS, 100 KB / 2 MB carried context), `zeroS`, `zeroL` (zero,
100 KB / 2 MB), `pirustS`, `pirustL` (pi-rust, wall only). Each cell: **one ingest,
then ten PONG turns.**

## Setup (once)

```sh
mkdir -p "$ROOT"/piS "$ROOT"/piL "$ROOT"/zeroL "$ROOT"/pirustS "$ROOT"/pirustL
head -c  102400 "$ROOT"/BIGFILE.txt > "$ROOT"/piS/SMALL.txt
head -c 2097152 "$ROOT"/BIGFILE.txt > "$ROOT"/piL/LARGE.txt
head -c 2097152 "$ROOT"/BIGFILE.txt > "$ROOT"/zeroL/LARGE.txt
head -c  102400 "$ROOT"/BIGFILE.txt > "$ROOT"/pirustS/SMALL.txt
head -c 2097152 "$ROOT"/BIGFILE.txt > "$ROOT"/pirustL/LARGE.txt
# zeroS already exists with SMALL.txt. zeroL is a NEW session (fresh session + LARGE).
CSV=${CSV:-bench.csv}
echo "harness,size,run,wall_s,llm_ms,total_ms,unacc_ms,in_tok,cache_tok,out_tok,notes" > "$CSV"
```

## Cells

One ingest + ten PONGs per cell. Exact prompts, unchanged:

- **piS** (pi-TS, `deepseek-v4.1-flash`, cwd `$ROOT/piS`)
  - ingest: `pi -p --provider opencode-go --model deepseek-v4.1-flash "Read the entire SMALL.txt and then reply with exactly the word DONE. Call no other tools."`
  - pong ×10: note T0 with `date -u +%FT%TZ`, then
    `time pi -p --provider opencode-go --model deepseek-v4.1-flash -c "Reply with exactly the word PONG. Call no tools."`
  - row: read `.pi-web/tps-turns.jsonl`, take the first turn with `ts >= T0`, and join the
    `history` file for cache tokens (`llm_ms`, `total_ms`, `unacc_ms`, `in_tok`).
- **piL**: same as piS with `LARGE.txt` in `$ROOT/piL`.
- **zeroS** (already exists, 100 KB): ten PONGs,
  `time zero exec --resume --auto medium -o stream-json "Reply with exactly the word PONG. Call no tools."`,
  parsing `usage` (`promptTokens`, `cached`, `completion`) from the JSON.
- **zeroL** (new): ingest `LARGE.txt`, then ten PONGs as above.
- **pirustS / pirustL**: `pi-rust -p --provider deepseek --model deepseek-chat --yolo`
  (ingest as pi); PONGs with `-c`. No token rows — wall plus a `wall-only` note.

**Retry rule:** a failed run is retried once; three failures in one cell marks the cell
`FAIL` and the series moves on to the next cell.

## Deliverable of the series

The CSV above, plus a per-cell table of means (wall; `unacc`/`llm` where they exist;
tokens), the anomalies, and the estimated spend.

# PROTOCOLO GRINDER — benchmark transcript-tax n=10
Trabajo ciego y continuo. NO toques: e095-tps-monitor, p4 git, .secrets, claves reales (solo NOMBRES de env vars en logs).
Techo: si estimas >$15 acumulados, para y reporta.

## Setup (una vez)
mkdir -p /tmp/duel/piS /tmp/duel/piL /tmp/duel/zeroL /tmp/duel/pirustS /tmp/duel/pirustL
head -c 102400 /tmp/octest/BIGFILE.txt > /tmp/duel/piS/SMALL.txt
head -c 2097152 /tmp/octest/BIGFILE.txt > /tmp/duel/piL/LARGE.txt
head -c 2097152 /tmp/octest/BIGFILE.txt > /tmp/duel/zeroL/LARGE.txt
head -c 102400 /tmp/octest/BIGFILE.txt > /tmp/duel/pirustS/SMALL.txt
head -c 2097152 /tmp/octest/BIGFILE.txt > /tmp/duel/pirustL/LARGE.txt
# zeroS ya existe con SMALL.txt. zeroL es sesión NUEVA (sesión fresca + LARGE).
CSV=/tmp/night/bench.csv ; echo "harness,size,run,wall_s,llm_ms,total_ms,unacc_ms,in_tok,cache_tok,out_tok,notes" > $CSV

## Celdas (para cada una: 1 ingest + 10 PONGs; salidas ULTRA-terras, solo fallos por pantalla)
### piS (pi-TS, deepseek-v4.1-flash, cwd /tmp/duel/piS)
ingest: pi -p --provider opencode-go --model deepseek-v4.1-flash "Read the entire SMALL.txt and then reply with exactly the word DONE. Call no other tools."
pong x10: date -u +%FT%TZ (anota T0); time pi -p --provider opencode-go --model deepseek-v4.1-flash -c "Reply with exactly the word PONG. Call no tools."
  fila: python3 -c "import json;ts=[json.loads(l) for l in open('.pi-web/tps-turns.jsonl')];t=[x for x in ts if x['ts']>='T0'][0];print(...)" (llm,total,unacc,input) + history join para cache.
### piL: igual con LARGE.txt en /tmp/duel/piL
### zeroS (existe, 100KB): 10 PONGs: time zero exec --resume --auto medium -o stream-json "Reply..." ; parse usage (promptTokens,cached,completion) del JSON.
### zeroL (nueva): ingest LARGE + 10 PONGs igual.
### pirustS/pirustL: pi-rust -p --provider deepseek --model deepseek-chat --yolo (ingest igual que pi); PONGs con -c. Sin filas: wall + nota wall-only.
Reintentos: fallo de run → reintenta 1 vez; 3 fallos en una celda → marca FAIL y sigue a la siguiente celda.

## Entrega (mensaje final): ruta CSV + tabla medias por celda (wall, unacc/llm si hay, tokens) + anomalías + gasto estimado.

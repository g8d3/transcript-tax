/* Parity test: roi.js (what the audit page runs) vs tools/roi.py (what we quote).
 *
 * The page must not be able to print a number the script disagrees with, so this
 * runs both over a grid of inputs and compares every field, plus the displayed
 * strings and the pay/no verdict.
 *
 *   node tests/roi-parity.mjs
 */
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
const require = createRequire(import.meta.url);
const HERE0 = new URL(".", import.meta.url).pathname;
// roi.js sits beside this pack (sales/roi.js) or at tools/roi.js in the public repo
const ROI_JS = [HERE0 + "../roi.js", HERE0 + "../tools/roi.js"].find((f) => fs.existsSync(f));
if (!ROI_JS) { console.log("FAIL: roi.js not found"); process.exit(1); }
const roi = require(ROI_JS);

const HERE = HERE0;
const PY = process.env.PYTHON || "python3";

const cases = [];
const push = (o) => cases.push(o);

// 1. exact sweep classes x fleets (same table as `roi.py --sweep`)
const classes = [
  { priceIn: 0.27, priceCache: 0.07, priceOut: 1.1, name: "cheap" },
  { priceIn: 3.0, priceCache: 0.3, priceOut: 15.0, name: "mid" },
  { priceIn: 15.0, priceCache: 1.5, priceOut: 75.0, name: "premium" },
];
for (const [agents, turns] of [[3, 60], [10, 100], [30, 200], [100, 200]]) {
  for (const c of classes) {
    for (const hourly of [0, 25, 50]) {
      push({ agents, turns, priceIn: c.priceIn, priceCache: c.priceCache, priceOut: c.priceOut, hourly });
    }
  }
}
// 2. boundaries and odd shapes
for (const v of [0, 1, 2, 7, 13.5, 99]) push({ agents: v, turns: 1 + v, days: 200 + v, hourly: v });
for (const cacheHit of [0, 0.25, 0.5, 0.7, 0.95, 1]) push({ cacheHit, hourly: 0, tier: 290 });
for (const warm of [true, false]) push({ warm, hourly: 60, tier: 3900, cutInput: 0.5, cutWall: 0.4 });
push({ inTok: 1 }); push({ inTok: 1e7, outTok: 1e5 });
push({ floorS: 0 }); push({ missRate: 0, missPenaltyS: 0 }); push({ missRate: 1, missPenaltyS: 30 });
push({ wasted: 0 }); push({ wasted: 1 });
push({ tier: 0 }); push({ tier: 1 }); push({ hourly: 0, cutInput: 0 }); push({ cutInput: 1, cutWall: 1 });
push({ cutWall: 0, hourly: 120 });
push({ days: 1, turns: 1, agents: 1 });

const gridPath = "/tmp/roi-parity-grid.json";
fs.writeFileSync(gridPath, JSON.stringify(cases));
const pyOut = execFileSync(PY, [HERE + "roi_grid.py", gridPath], { encoding: "utf8" })
  .trim().split("\n").map((l) => JSON.parse(l));

const NUM_FIELDS = ["turns_year", "per_turn", "year_tokens", "wall_per_turn", "year_hours",
  "boot_hours", "floor_hours", "miss_hours", "boot_per_turn", "waste_tokens",
  "in_saved", "wall_saved", "time_value", "saved", "payback_days"];
// camelCase twins in roi.js
const JS_FIELD = {
  turns_year: "turnsYear", per_turn: "perTurn", year_tokens: "yearTokens",
  wall_per_turn: "wallPerTurn", year_hours: "yearHours", boot_hours: "bootHours",
  floor_hours: "floorHours", miss_hours: "missHours", boot_per_turn: "bootPerTurn",
  waste_tokens: "wasteTokens", in_saved: "inSaved", wall_saved: "wallSaved",
  time_value: "timeValue", saved: "saved", payback_days: "paybackDays",
};

let fails = 0, checked = 0;
const fail = (msg) => { if (fails < 15) console.log("FAIL " + msg); fails++; };
const close = (a, b) => {
  if (a === b) return true;                        // covers Infinity === Infinity
  if (a === null || b === null || !isFinite(a) || !isFinite(b)) return false;
  const scale = Math.max(1, Math.abs(a), Math.abs(b));
  return Math.abs(a - b) <= 1e-9 * scale;
};

cases.forEach((input, i) => {
  const py = pyOut[i];
  if (!py) { fail(`no python row for case ${i}`); return; }
  const r = roi.computeROI(input);
  for (const f of NUM_FIELDS) {
    const mine = r[JS_FIELD[f]];
    const theirs = py.out[f] === null ? Infinity : py.out[f];
    checked++;
    if (!close(mine, theirs)) fail(`case ${i} ${f}: js=${mine} py=${theirs} (in=${JSON.stringify(input)})`);
  }
  // displayed strings must match too, so the page cannot round differently
  const sMoney = roi.money(r.yearTokens), pMoney = py.out._money_year_tokens;
  if (sMoney !== pMoney) fail(`case ${i} money(yearTokens): js=${sMoney} py=${pMoney}`);
  const sSaved = roi.money(r.saved), pSaved = py.out._money_saved;
  if (sSaved !== pSaved) fail(`case ${i} money(saved): js=${sSaved} py=${pSaved}`);
  const sHours = roi.num(r.yearHours), pHours = py.out._hours0;
  if (sHours !== pHours) fail(`case ${i} yearHours fmt: js=${sHours} py=${pHours}`);
  // verdict must agree with the sweep flags: "pays" <=60 days, "no" >250 or never
  const v = roi.verdict(r, r.params.tier);
  const pyDays = py.out.payback_days === null ? Infinity : py.out.payback_days;
  const expect = pyDays <= 60 ? "pays" : pyDays <= 250 ? "marginal" : "no";
  if (v.key !== expect) fail(`case ${i} verdict: js=${v.key} py=${expect} (days=${pyDays})`);
});

// the sweep table the landing quotes must come out identical too
const sweepRows = classes.flatMap((c) =>
  [[3, 60], [10, 100], [30, 200], [100, 200]].map(([agents, turns]) => {
    const r = roi.computeROI({ agents, turns, priceIn: c.priceIn, priceCache: c.priceCache, priceOut: c.priceOut });
    return `Tile${c.name}|${agents}x${turns}|${roi.money(r.yearTokens)}|${roi.money(r.saved)}|${roi.num(r.paybackDays)}|${roi.verdict(r, 1400).key}`;
  }));
// the calculator lives at tools/roi.py in the public repo and at roi.py in this pack
const ROI_PY = [HERE + "../tools/roi.py", HERE + "../roi.py"].find((p) => fs.existsSync(p));
if (!ROI_PY) { console.log("FAIL: roi.py not found for the sweep comparison"); process.exit(1); }
const pySweep = execFileSync(PY, [ROI_PY, "--sweep"], { encoding: "utf8" });
for (const row of sweepRows) {
  const [, fleet, tokens, saved, days, key] = row.split("|");
  if (!pySweep.includes(tokens) || !pySweep.includes(saved)) {
    fail(`sweep row ${fleet} (${tokens}/${saved}) not found in tools/roi.py --sweep output`);
  }
  if (pySweep.includes(`${days}  <- pays`) && key !== "pays") fail(`sweep ${fleet}: script says pays, page says ${key}`);
}

// the page must embed this exact source, or the page can drift from the tested file
const LANDING = [HERE0 + "../landing.html", HERE0 + "../audit/index.html"].find((f) => fs.existsSync(f));
if (LANDING) {
  const html = fs.readFileSync(LANDING, "utf8");
  if (!html.includes(fs.readFileSync(ROI_JS, "utf8"))) {
    fail(`${LANDING} does not embed ${ROI_JS} verbatim — rebuild with build_landing.py`);
  }
  // form defaults must equal roi.js DEFAULTS
  for (const [id, key] of [["agents", "agents"], ["turns", "turns"], ["inTok", "inTok"],
    ["priceIn", "priceIn"], ["priceCache", "priceCache"], ["priceOut", "priceOut"],
    ["floorS", "floorS"], ["bootS", "bootS"], ["missPenaltyS", "missPenaltyS"], ["tier", "tier"]]) {
    const m = html.match(new RegExp(`id="${id}"[^>]*value="([^"]+)"`));
    if (!m) { fail(`landing.html has no #${id} default`); continue; }
    const expected = roi.DEFAULTS[key];
    if (Math.abs(Number(m[1]) - expected) > 1e-9) fail(`#${id} default ${m[1]} != roi.js default ${expected}`);
  }
  for (const [id, key, scale] of [["cacheHitPct", "cacheHit", 100], ["missRatePct", "missRate", 100],
    ["wastedPct", "wasted", 100], ["cutInputPct", "cutInput", 100], ["cutWallPct", "cutWall", 100]]) {
    const m = html.match(new RegExp(`id="${id}"[^>]*value="([^"]+)"`));
    if (!m) { fail(`landing.html has no #${id} default`); continue; }
    if (Math.abs(Number(m[1]) / scale - roi.DEFAULTS[key]) > 1e-9) {
      fail(`#${id} default ${m[1]}% != roi.js default ${roi.DEFAULTS[key]}`);
    }
  }
  console.log(`landing check: ${LANDING.split("/").slice(-2).join("/")} embeds roi.js and its defaults match`);
}

console.log(`cases=${cases.length} numeric checks=${checked} failures=${fails}`);
console.log(fails === 0 ? "PARITY OK" : "PARITY FAILED");
process.exit(fails ? 1 : 0);

/* ROI calculator — the browser twin of tools/roi.py (same arithmetic, same defaults).
 *
 * It exists so a prospect can price the audit on their own numbers without
 * installing anything. Every default here is identical to the argparse defaults
 * in tools/roi.py; tests/roi-parity.mjs checks the two agree over a grid of
 * inputs (numbers, verdicts and the displayed strings).
 *
 * No tracking, no external requests, no dependencies.
 */
(function (root) {
  "use strict";

  var DEFAULTS = {
    // fleet shape
    agents: 10,
    turns: 100,
    days: 250,
    // per-turn tokens
    inTok: 40000,
    outTok: 400,
    cacheHit: 0.7,
    // prices, USD per 1M tokens (defaults = DeepSeek list; replace with yours)
    priceIn: 0.27,
    priceCache: 0.07,
    priceOut: 1.1,
    // measured timing
    floorS: 3.0,
    bootS: 0.93,
    warm: false,
    missRate: 0.3,
    missPenaltyS: 5.0,
    wasted: 0.1,
    // what the audit is expected to move (conservative)
    cutInput: 0.35,
    cutWall: 0.2,
    // money
    hourly: 0,
    tier: 1400
  };

  function withDefaults(o) {
    var out = {};
    for (var k in DEFAULTS) out[k] = DEFAULTS[k];
    for (var k2 in o || {}) if (o[k2] !== undefined && o[k2] !== null && o[k2] !== "") out[k2] = o[k2];
    return out;
  }

  /* Port of compute() in tools/roi.py. Keep the two in step. */
  function computeROI(options) {
    var a = withDefaults(options);
    var turnsYear = a.agents * a.turns * a.days;

    var miss = 1 - a.cacheHit;
    var inCost = (a.inTok / 1e6) * (miss * a.priceIn + a.cacheHit * a.priceCache);
    var outCost = (a.outTok / 1e6) * a.priceOut;
    var perTurn = inCost + outCost;
    var yearTokens = turnsYear * perTurn;

    var bootPerTurn = a.warm ? 0 : a.bootS;
    var wallPerTurn = bootPerTurn + a.floorS + a.missRate * a.missPenaltyS;
    var yearHours = (turnsYear * wallPerTurn) / 3600;
    var bootHours = (turnsYear * bootPerTurn) / 3600;
    var floorHours = (turnsYear * a.floorS) / 3600;
    var missHours = (turnsYear * a.missRate * a.missPenaltyS) / 3600;
    var wallAfter = yearHours * (1 - a.cutWall);

    var wasteTokens = turnsYear * a.wasted * perTurn;

    var inSaved = turnsYear * ((a.inTok * a.cutInput) / 1e6) * (miss * a.priceIn + a.cacheHit * a.priceCache);
    var wallSaved = yearHours - wallAfter;
    var timeValue = wallSaved * a.hourly;
    var saved = inSaved + timeValue;
    var paybackDays = saved > 0 ? (a.tier / saved) * a.days : Infinity;

    return {
      turnsYear: turnsYear,
      perTurn: perTurn,
      yearTokens: yearTokens,
      wallPerTurn: wallPerTurn,
      yearHours: yearHours,
      bootHours: bootHours,
      floorHours: floorHours,
      missHours: missHours,
      bootPerTurn: bootPerTurn,
      wasteTokens: wasteTokens,
      inSaved: inSaved,
      wallSaved: wallSaved,
      timeValue: timeValue,
      saved: saved,
      paybackDays: paybackDays,
      params: a
    };
  }

  /* Round like Python's format(): ties go to even, not up.
   *
   * The two languages agree on every non-tie, and a tie only happens when the
   * value is exactly on the boundary in decimal (e.g. 2262.5 hours). Python
   * rounds that to 2,262 and Math.round would say 2,263, so the script and the
   * page would quote different numbers for the same input. tests/roi-parity.mjs
   * fails if they ever drift. */
  function roundHalfEven(x, digits) {
    var f = Math.pow(10, digits);
    var scaled = x * f;
    var floor = Math.floor(scaled);
    var frac = scaled - floor;
    if (frac === 0.5) return (floor % 2 === 0 ? floor : floor + 1) / f;
    return Math.round(scaled) / f;
  }

  function group(intStr) {
    return intStr.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  /* tools/roi.py money(): no cents at $1000+, two decimals below. */
  function money(usd) {
    if (!isFinite(usd)) return "never";
    if (Math.abs(usd) >= 1000) {
      return (usd < 0 ? "-" : "") + "$" + group(String(roundHalfEven(Math.abs(usd), 0)));
    }
    return (usd < 0 ? "-" : "") + "$" + Math.abs(roundHalfEven(usd, 2)).toFixed(2);
  }

  function num(v, digits) {
    if (!isFinite(v)) return "never";
    var d = digits || 0;
    var r = roundHalfEven(v, d);
    var s = Math.abs(r).toFixed(d);
    var parts = s.split(".");
    var out = group(parts[0]) + (parts[1] ? "." + parts[1] : "");
    return (r < 0 || Object.is(r, -0) ? "-" : "") + out;
  }

  /* Same thresholds and words as the Python sweep, so the page cannot claim a
   * fleet pays when the script says it does not. */
  function verdict(r, tier) {
    if (r.paybackDays <= 60) return { key: "pays", label: "pays for itself in " + num(r.paybackDays) + " working days" };
    if (r.paybackDays <= 250) return { key: "marginal", label: "pays back in " + num(r.paybackDays) + " working days: inside a year, not obviously a buy" };
    if (!isFinite(r.paybackDays)) return { key: "no", label: "does not pay back at these numbers: we would say no" };
    return { key: "no", label: "does not pay back (" + num(r.paybackDays) + " working days): we would say no" };
  }

  var api = { DEFAULTS: DEFAULTS, computeROI: computeROI, money: money, num: num, verdict: verdict };
  root.TPS_ROI = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);

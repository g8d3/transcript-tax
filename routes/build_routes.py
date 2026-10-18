#!/usr/bin/env python3
"""Build the published route-dispersion page from the measured matrix.

    python3 build_routes.py     -> routes/routes.html (self-contained, deployable as-is)

Same HTML path as the delivery engine (`audit_report.to_html`), so the page we publish and
the reports we hand a client share their renderer. The numbers are not typed here: they come
from `routes/MATRIX.md`, which `routes/render_matrix.py` writes from `routes/matrix.json`,
which `routes/matrix.py` measures.
"""
from __future__ import annotations
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from audit_report import to_html  # noqa: E402

ROUTES = HERE / "routes"
OUT = ROUTES / "routes.html"
BANNER = """
<div class="banner"><strong>Same model, different route.</strong> Measured 2026-10-18 on one
machine, two calls per route, streaming (first token and total are separate numbers). Prices are
the ones each provider publishes in its own <code>/models</code> metadata; a route that publishes
none says so. This is a dispersion probe, not a benchmark, and the page states its limits.
Raw rows: <code>routes/matrix.json</code>. Re-run <code>routes/matrix.py</code> before quoting
a price.</div>
"""


def main() -> None:
    md = (ROUTES / "MATRIX.md").read_text()
    html = to_html(md, BANNER, title="Provider matrix — the same model, several routes",
                   description="Price and first-token latency for one model across several "
                               "providers, measured, with the limits stated.")
    if "«" in html:
        raise SystemExit("an unfilled placeholder reached the published page")
    OUT.write_text(html)
    print(f"wrote {OUT.name} ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()

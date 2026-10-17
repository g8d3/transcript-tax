#!/usr/bin/env python3
"""Build article.html: the report as one self-contained, paste-ready page.

  python3 build_article.py

Figures are inlined as base64 so the single file can be pasted into any blog,
CMS or email without asset hosting. Nothing is published by this script.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

import markdown

HERE = Path(__file__).parent
OUT = HERE / "article.html"

CSS = """
:root { color-scheme: light dark; }
body { max-width: 46rem; margin: 3rem auto; padding: 0 1.2rem;
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
h1 { font-size: 1.9rem; line-height: 1.25; margin-bottom: .3rem; }
h2 { margin-top: 2.4rem; border-top: 1px solid color-mix(in srgb, currentColor 18%, transparent); padding-top: 1.2rem; }
h3 { margin-top: 1.8rem; }
table { border-collapse: collapse; width: 100%; margin: 1.2rem 0; font-size: .93rem; display: block; overflow-x: auto; }
th, td { border: 1px solid color-mix(in srgb, currentColor 25%, transparent); padding: .4rem .55rem; text-align: left; }
th { background: color-mix(in srgb, currentColor 8%, transparent); }
img { max-width: 100%; height: auto; margin: 1.2rem 0; }
code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .9em; }
pre { background: color-mix(in srgb, currentColor 7%, transparent); padding: .8rem; overflow-x: auto; }
blockquote { border-left: 3px solid color-mix(in srgb, currentColor 35%, transparent);
  margin: 1.4rem 0; padding: .2rem 0 .2rem 1rem; }
em { color: color-mix(in srgb, currentColor 80%, transparent); }
footer { margin-top: 3rem; font-size: .85rem; opacity: .75; }
"""


def inline_images(html: str) -> str:
    def repl(m: re.Match) -> str:
        src = m.group(1)
        p = HERE / src
        if not p.exists():
            return m.group(0)
        b64 = base64.b64encode(p.read_bytes()).decode()
        return f'src="data:image/png;base64,{b64}"'

    return re.sub(r'src="([^"]+\.png)"', repl, html)


def main() -> None:
    text = (HERE / "REPORT.md").read_text()
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    body = inline_images(body)
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transcript Tax 2026 — what a trivial agent turn really costs</title>
<style>{CSS}</style></head>
<body>
{body}
<footer>Source, data and reproduction: <code>bench.csv</code> + <code>analyze.py</code> in this
repository. Text and data CC BY 4.0. Figures are inlined; the page has no external requests.</footer>
</body></html>
"""
    OUT.write_text(html)
    kb = len(html) / 1024
    print(f"wrote {OUT.name} ({kb:.0f} KB, figures inlined, no external requests)")


if __name__ == "__main__":
    main()

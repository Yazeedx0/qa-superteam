"""axe-core accessibility scan via Playwright (Python). Run with the project's interpreter.

    python -m qa_superteam.runners.axe_scan --axe node_modules/axe-core/axe.min.js \
        --url http://127.0.0.1:8000/ --out result.json --shots DIR [--viewport 375x812]

Exit codes: 0 scan completed (violations or not), 3 playwright missing, 4 navigation error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def launch_chromium(p):
    """Launch Playwright's Chromium; if the pinned build is missing, fall back to
    CHROMIUM_EXECUTABLE or the newest Chromium in the Playwright cache."""
    import glob
    import os

    exe = os.environ.get("CHROMIUM_EXECUTABLE")
    if exe:
        return p.chromium.launch(executable_path=exe)
    try:
        return p.chromium.launch()
    except Exception as first:  # noqa: BLE001
        cache = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or os.path.expanduser("~/.cache/ms-playwright")
        cands = sorted(glob.glob(os.path.join(cache, "chromium-*", "chrome-*", "chrome")), reverse=True)
        if not cands:
            raise first
        print(f"note: pinned Chromium missing; using {cands[0]}", file=sys.stderr)
        return p.chromium.launch(executable_path=cands[0])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--axe", required=True)
    ap.add_argument("--url", action="append", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--shots", required=True)
    ap.add_argument("--viewport", default="1280x800")
    ap.add_argument("--wait-ms", type=int, default=300)
    ap.add_argument("--tags", default="wcag2a,wcag2aa,wcag21a,wcag21aa,wcag22aa")
    args = ap.parse_args(argv)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed for this interpreter", file=sys.stderr)
        return 3
    w, h = (int(x) for x in args.viewport.lower().split("x"))
    axe_src = Path(args.axe).read_text(encoding="utf-8")
    pages = []
    with sync_playwright() as p:
        browser = launch_chromium(p)
        try:
            ctx = browser.new_context(viewport={"width": w, "height": h})
            for url in args.url:
                page = ctx.new_page()
                try:
                    page.goto(url, wait_until="networkidle", timeout=30_000)
                except Exception as e:  # noqa: BLE001
                    pages.append({"url": url, "error": f"navigation failed: {e}"})
                    page.close()
                    continue
                page.wait_for_timeout(args.wait_ms)
                page.add_script_tag(content=axe_src)
                result = page.evaluate(
                    "async (tags) => await axe.run(document, {runOnly: {type: 'tag', values: tags}, resultTypes: ['violations','incomplete']})",
                    args.tags.split(","),
                )
                shot = Path(args.shots) / (re.sub(r"[^a-zA-Z0-9]+", "-", url).strip("-")[:80] + ".png")
                page.screenshot(path=str(shot), full_page=True)

                def slim(items):
                    return [
                        {
                            "id": v["id"],
                            "impact": v.get("impact"),
                            "help": v.get("help"),
                            "helpUrl": v.get("helpUrl"),
                            "nodes": [{"target": n.get("target"), "html": (n.get("html") or "")[:300], "summary": (n.get("failureSummary") or "")[:500]} for n in v.get("nodes", [])[:10]],
                        }
                        for v in items
                    ]

                pages.append(
                    {
                        "url": url,
                        "violations": slim(result.get("violations", [])),
                        "incomplete": slim(result.get("incomplete", [])),
                        "passes": [v["id"] for v in result.get("passes", [])],
                        "axe_version": (result.get("testEngine") or {}).get("version"),
                        "screenshot": shot.name,
                    }
                )
                page.close()
        finally:
            browser.close()
    Path(args.out).write_text(json.dumps({"pages": pages, "viewport": args.viewport}, indent=2), encoding="utf-8")
    return 4 if pages and all("error" in pg for pg in pages) else 0


if __name__ == "__main__":
    raise SystemExit(main())

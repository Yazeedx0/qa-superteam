#!/usr/bin/env python3
"""Export JSON Schemas for the record models (schemas/*.schema.json).

    python3 scripts/gen_schemas.py          # write
    python3 scripts/gen_schemas.py --check  # fail if committed schemas drift from models.py (CI)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qa_superteam.models import EXPORTED_MODELS  # noqa: E402
from qa_superteam.serde import json_schema  # noqa: E402

BASE = "https://qa-superteam.dev/schemas/"


def main() -> int:
    check = "--check" in sys.argv
    out_dir = ROOT / "schemas"
    out_dir.mkdir(exist_ok=True)
    drift = []
    expected = set()
    for name, cls in sorted(EXPORTED_MODELS.items()):
        fname = f"{name}.schema.json"
        expected.add(fname)
        text = json.dumps(json_schema(cls, BASE + fname), indent=2, ensure_ascii=False) + "\n"
        path = out_dir / fname
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                drift.append(fname)
        else:
            path.write_text(text, encoding="utf-8")
    stale = sorted(p.name for p in out_dir.glob("*.schema.json") if p.name not in expected)
    if check:
        if drift or stale:
            print("schema drift: " + ", ".join(drift + stale) + "\nrun: python3 scripts/gen_schemas.py")
            return 1
        print(f"schemas up to date ({len(expected)})")
        return 0
    for s in stale:
        (out_dir / s).unlink()
    print(f"wrote {len(expected)} schemas to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

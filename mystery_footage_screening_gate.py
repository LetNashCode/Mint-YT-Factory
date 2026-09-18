"""Fail the workflow when no screened candidate is safe to process."""
from __future__ import annotations

import json
import sys
from pathlib import Path

CATALOG = Path(__file__).resolve().parent / "mystery_footage_catalog.json"


def main() -> None:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    items = data.get("items", [])
    eligible = []
    for item in items:
        screening = item.get("screening") or {}
        if screening.get("eligible") is True:
            eligible.append(item.get("id"))
            continue
        # Preserve manually curated, rights-verified cases.
        if item.get("rights_verified") is True:
            eligible.append(item.get("id"))
    if not eligible:
        print("No screened or rights-verified mystery footage candidate is available.", file=sys.stderr)
        raise SystemExit(1)
    print(f"Screening gate passed with {len(eligible)} eligible candidate(s): {', '.join(eligible)}")


if __name__ == "__main__":
    main()

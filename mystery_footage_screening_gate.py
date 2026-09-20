"""Report whether mystery footage passed the required screening gate."""
from __future__ import annotations

import json
import os
from pathlib import Path

CATALOG = Path(__file__).resolve().parent / "mystery_footage_catalog.json"


def write_output(eligible: bool) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(f"eligible={'true' if eligible else 'false'}\n")


def main() -> None:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    items = data.get("items", [])
    eligible = [
        item.get("id")
        for item in items
        if (item.get("screening") or {}).get("eligible") is True
    ]

    if not eligible:
        write_output(False)
        print("No mystery footage candidate passed the required screening gate; skipping production for this run.")
        return

    write_output(True)
    print(f"Screening gate passed with {len(eligible)} eligible candidate(s): {', '.join(eligible)}")


if __name__ == "__main__":
    main()

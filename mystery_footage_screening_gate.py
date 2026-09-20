"""Report whether an unused mystery footage case passed screening."""
from __future__ import annotations

import json
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "mystery_footage_catalog.json"
HISTORY = ROOT / "mystery_footage_history.json"


def write_output(eligible: bool) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(f"eligible={'true' if eligible else 'false'}\n")


def main() -> None:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else {}
    used = {str(item) for item in history.get("used_item_ids", [])}
    eligible = [
        str(item.get("id"))
        for item in data.get("items", [])
        if (item.get("screening") or {}).get("eligible") is True
        and str(item.get("id")) not in used
    ]

    if not eligible:
        write_output(False)
        print("No unused mystery footage candidate passed the screening gate; skipping production for this run.")
        return

    write_output(True)
    print(f"Screening gate passed with {len(eligible)} unused eligible candidate(s): {', '.join(eligible)}")


if __name__ == "__main__":
    main()

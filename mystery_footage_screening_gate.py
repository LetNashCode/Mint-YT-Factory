"""Report whether mystery footage is ready without failing empty scheduled runs."""
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
    eligible = []
    for item in items:
        screening = item.get("screening") or {}
        if screening.get("eligible") is True:
            eligible.append(item.get("id"))
            continue
        if item.get("rights_verified") is True:
            eligible.append(item.get("id"))

    if not eligible:
        write_output(False)
        print("No screened or rights-verified mystery footage candidate is available; skipping production for this run.")
        return

    write_output(True)
    print(f"Screening gate passed with {len(eligible)} eligible candidate(s): {', '.join(eligible)}")


if __name__ == "__main__":
    main()

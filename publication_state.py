"""Crash-safe publication state for Story Shorts uploads."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


def load(path: str) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"status": "pending", "platforms": {}}
    return json.loads(target.read_text(encoding="utf-8"))


def save(path: str, state: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=str(target.parent), delete=False) as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, target)


def mark_platform(path: str, platform: str, status: str, **details: Any) -> dict[str, Any]:
    state = load(path)
    platforms = state.setdefault("platforms", {})
    record = dict(platforms.get(platform) or {})
    record.update(details)
    record["status"] = status
    platforms[platform] = record
    state["status"] = "published" if platforms and all(item.get("status") == "published" for item in platforms.values()) else "partial"
    save(path, state)
    return state

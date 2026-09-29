"""Select and produce a never-before-used Mystery Documentary case."""
from __future__ import annotations
import json, os, re, runpy, subprocess, tempfile, time
from pathlib import Path
import requests
ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "mystery_footage_catalog.json"
HISTORY = ROOT / "mystery_footage_history.json"

def load_history() -> dict:
    if not HISTORY.exists(): return {"used_item_ids": [], "entries": []}
    try:
        data=json.loads(HISTORY.read_text(encoding="utf-8"))
        data.setdefault("used_item_ids",[])
        data.setdefault("entries",[])
        return data
    except (json.JSONDecodeError,OSError):
        return {"used_item_ids": [], "entries": []}

def reserve_history_item(item: dict) -> None:
    """Persist a case reservation without consuming it until YouTube publication."""
    history = load_history()
    item_id = str(item.get("id") or "").strip()
    if not item_id:
        raise RuntimeError("Mystery case has no catalog item id")
    if item_id in {str(x) for x in history.get("used_item_ids", [])}:
        return
    for entry in history.get("entries", []):
        if isinstance(entry, dict) and str(entry.get("item_id") or "") == item_id:
            if str(entry.get("status") or "") in {"reserved", "published"}:
                return
    history["entries"] = [*history.get("entries", []), {
        "item_id": item_id,
        "title": item.get("title", ""),
        "source_url": item.get("source_url", ""),
        "reserved_at": int(time.time()),
        "status": "reserved",
    }]
    HISTORY.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def mark_history_published(item_id: str, video_id: str = "") -> bool:
    """Convert a reserved Mystery case to durable used history after upload."""
    item_id = str(item_id or "").strip()
    if not item_id:
        return False
    history = load_history()
    used = {str(x) for x in history.get("used_item_ids", [])}
    used.add(item_id)
    history["used_item_ids"] = sorted(used)
    found = False
    for entry in history.get("entries", []):
        if isinstance(entry, dict) and str(entry.get("item_id") or "") == item_id:
            entry.update({"status": "published", "published_at": int(time.time()), "video_id": str(video_id or "")})
            found = True
    if not found:
        history["entries"].append({"item_id": item_id, "status": "published", "published_at": int(time.time()), "video_id": str(video_id or "")})
    HISTORY.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True

def _source_key(value: str) -> str:
    value = str(value or "").strip().lower()
    return re.sub(r"[?#].*$", "", value).rstrip("/")


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    history = load_history()
    used = {str(x) for x in history.get("used_item_ids", [])}
    used_sources = {
        _source_key(entry.get("source_url"))
        for entry in history.get("entries", [])
        if isinstance(entry, dict) and _source_key(entry.get("source_url"))
        and str(entry.get("status") or "").lower() in {"reserved", "published"}
    }
    candidates = [
        x for x in catalog.get("items", [])
        if x.get("video_url")
        and x.get("source_url")
        and (x.get("screening") or {}).get("eligible") is True
        and str(x.get("id")) not in used
        and _source_key(x.get("source_url")) not in used_sources
    ]
    requested = os.getenv("MYSTERY_FOOTAGE_ITEM_ID", "").strip()
    if requested:
        candidates = [x for x in candidates if str(x.get("id")) == requested]
    if not candidates:
        print("MYSTERY_DOCUMENTARY_SKIPPED=no unused eligible case")
        return

    from factory_content_memory import claim as claim_factory_topic

    # Topic uniqueness is global. If a newly discovered source describes the same
    # mystery as an already published/reserved factory topic, skip it and continue
    # to the next candidate instead of crashing or repeating an old documentary.
    selected = None
    item_id = ""
    factory_topic = ""
    for candidate in candidates:
        candidate_id = str(candidate.get("id") or "").strip()
        try:
            duration, width, height = _preflight_source(candidate)
            print(
                f"✅ Mystery source preflight passed | "
                f"{candidate.get('title', candidate_id)} | {duration:.2f}s | {width}x{height}",
                flush=True,
            )
        except Exception as exc:
            print(
                f"⏭️ Skipping unusable Mystery source before topic reservation | "
                f"{candidate.get('title', candidate_id)} | {exc}",
                flush=True,
            )
            continue

        candidate_topic = f"{candidate.get('title','')}: {candidate.get('case_summary','')}".strip(": ")
        try:
            claim_factory_topic(
                "mystery",
                candidate_topic,
                {
                    "item_id": candidate_id,
                    "source_url": candidate.get("source_url", ""),
                    "source": "mystery_case_selection",
                    "source_duration_seconds": round(duration, 2),
                    "source_width": width,
                    "source_height": height,
                },
            )
            selected = candidate
            item_id = candidate_id
            factory_topic = candidate_topic
            break
        except RuntimeError as exc:
            print(
                f"⏭️ Skipping duplicate Mystery topic | "
                f"{candidate.get('title', candidate_id)} | {exc}",
                flush=True,
            )
    if selected is None:
        print("MYSTERY_DOCUMENTARY_SKIPPED=no unused unique mystery case")
        return

    os.environ["MYSTERY_FOOTAGE_ITEM_ID"] = item_id

    # The case/topic is locked before learning context is refreshed or expensive rendering begins.
    try:
        from factory_content_memory import refresh_learning, learning_context, select_strategy
        learning = refresh_learning()
        os.environ["MINT_FACTORY_LEARNING_CONTEXT"] = learning_context(max_chars=4500)
        os.environ["MINT_FACTORY_CREATIVE_STRATEGY"] = json.dumps(select_strategy(), ensure_ascii=False)
        print(
            f"🧠 Factory learning refreshed after Mystery case lock: videos={learning.get('analytics',{}).get('video_count',0)} "
            f"| ready={learning.get('playbook',{}).get('learning_ready',False)}",
            flush=True,
        )
    except Exception as exc:
        print(f"⚠️ Mystery factory learning refresh skipped: {type(exc).__name__}: {exc}", flush=True)

    output_dir = ROOT / os.getenv("MYSTERY_DOCUMENTARY_OUTPUT_DIR", "artifacts/mystery-documentary")
    metadata_path = output_dir / "metadata.json"
    output_path = output_dir / "mystery-documentary.mp4"
    try:
        runpy.run_module("mystery_documentary_scene_renderer", run_name="__main__")
        if not output_path.exists() or output_path.stat().st_size < 100_000:
            raise RuntimeError(
                "Mystery Documentary generation completed without a valid output video."
            )
        if not metadata_path.exists():
            raise RuntimeError(
                "Mystery Documentary generation completed without metadata.json."
            )
    except Exception:
        # A reserved topic must never remain locked when no documentary was produced.
        from factory_content_memory import release as release_factory_topic
        release_factory_topic(factory_topic, workflow="mystery")
        raise

    reserve_history_item(selected)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["history_recorded"] = False
    metadata["history_status"] = "reserved"
    metadata["factory_topic"] = factory_topic
    metadata["creative_strategy"] = os.getenv("MINT_FACTORY_CREATIVE_STRATEGY", "")
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"MYSTERY_DOCUMENTARY_GENERATED={output_path}")
    print(f"MYSTERY_DOCUMENTARY_HISTORY_RECORDED={item_id}")

if __name__ == "__main__":
    main()

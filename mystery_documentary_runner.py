"""Select and produce a never-before-used Mystery Documentary case."""
from __future__ import annotations
import json, os, runpy, time
from pathlib import Path
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

def main() -> None:
    try:
        from factory_content_memory import refresh_learning, learning_context, select_strategy
        learning = refresh_learning()
        os.environ["MINT_FACTORY_LEARNING_CONTEXT"] = learning_context(max_chars=4500)
        os.environ["MINT_FACTORY_CREATIVE_STRATEGY"] = json.dumps(select_strategy(), ensure_ascii=False)
        print(
            f"🧠 Factory learning refreshed: videos={learning.get('analytics',{}).get('video_count',0)} "
            f"| ready={learning.get('playbook',{}).get('learning_ready',False)}",
            flush=True,
        )
    except Exception as exc:
        print(f"⚠️ Mystery factory learning refresh skipped: {type(exc).__name__}: {exc}", flush=True)
    catalog=json.loads(CATALOG.read_text(encoding="utf-8")); history=load_history(); used={str(x) for x in history.get("used_item_ids",[])}
    candidates=[x for x in catalog.get("items",[]) if x.get("video_url") and x.get("source_url") and (x.get("screening") or {}).get("eligible") is True and str(x.get("id")) not in used]
    requested=os.getenv("MYSTERY_FOOTAGE_ITEM_ID","").strip()
    if requested: candidates=[x for x in candidates if str(x.get("id"))==requested]
    if not candidates: print("MYSTERY_DOCUMENTARY_SKIPPED=no unused eligible case"); return
    selected=candidates[0]
    item_id=str(selected["id"])
    os.environ["MYSTERY_FOOTAGE_ITEM_ID"]=item_id
    from factory_content_memory import claim as claim_factory_topic
    factory_topic = f"{selected.get('title','')}: {selected.get('case_summary','')}".strip(": ")
    claim_factory_topic(
        "mystery",
        factory_topic,
        {"item_id": item_id, "source_url": selected.get("source_url",""), "source": "mystery_case_selection"},
    )
    runpy.run_module("mystery_documentary_scene_renderer",run_name="__main__")
    output_dir=ROOT/os.getenv("MYSTERY_DOCUMENTARY_OUTPUT_DIR","artifacts/mystery-documentary"); metadata_path=output_dir/"metadata.json"
    reserve_history_item(selected)
    if metadata_path.exists():
        metadata=json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["history_recorded"]=False\n        metadata["history_status"]="reserved"
        metadata["factory_topic"]=factory_topic
        metadata["creative_strategy"]=os.getenv("MINT_FACTORY_CREATIVE_STRATEGY","")
        metadata_path.write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"MYSTERY_DOCUMENTARY_HISTORY_RECORDED={item_id}")
if __name__ == "__main__": main()

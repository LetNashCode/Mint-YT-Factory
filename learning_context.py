"""Build compact self-learning context for Gemini prompts."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLAYBOOK = ROOT / "analytics" / "playbook.json"


def load_learning_context(max_chars: int = 7000) -> str:
    try:
        data = json.loads(PLAYBOOK.read_text(encoding="utf-8"))
    except Exception:
        return "SELF-LEARNING DATA: not ready yet; make an original topic."

    if not isinstance(data, dict) or not data.get("learning_ready"):
        return "SELF-LEARNING DATA: warming up; prioritize originality and strong curiosity."

    lines = [
        "SELF-LEARNING CHANNEL PLAYBOOK",
        f"Published videos analyzed: {data.get('video_count', 0)}",
        "Objective: maximize sustainable views and subscriber growth.",
        "",
        "WINNING PATTERNS (learn these, do not copy topics):",
    ]
    for row in data.get("winning_patterns", [])[:10]:
        lines.append(f"- {row.get('pattern')}: score {row.get('score')} (n={row.get('sample_size')})")

    lines += ["", "WEAK PATTERNS TO AVOID:"]
    for row in data.get("weak_patterns", [])[:10]:
        lines.append(f"- {row.get('pattern')}: score {row.get('score')} (n={row.get('sample_size')})")

    lines += [
        "",
        "RECENT WINNING TOPICS (DO NOT REUSE):",
        *[f"- {x}" for x in data.get("winning_topics", [])[:8]],
        "",
        "RULES:",
        *[f"- {x}" for x in data.get("rules", [])],
    ]
    text = "\n".join(lines)
    return text[:max_chars]

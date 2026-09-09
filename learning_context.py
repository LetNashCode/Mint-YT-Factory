"""Build compact, evidence-weighted creative learning context for Gemini."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLAYBOOK = ROOT / "analytics" / "playbook.json"


def _evidence_rows(rows, limit=8):
    """Only expose patterns with repeated evidence; singles remain exploration data."""
    result = []
    for row in rows or []:
        try:
            n = int(row.get("sample_size", 0) or 0)
        except (TypeError, ValueError):
            n = 0
        if n < 2:
            continue
        pattern = str(row.get("pattern", "")).strip()
        if not pattern:
            continue
        try:
            score = float(row.get("score", 0) or 0)
        except (TypeError, ValueError):
            score = 0.0
        result.append((score, n, pattern))
    result.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return result[:limit]


def load_learning_context(max_chars: int = 7000) -> str:
    try:
        data = json.loads(PLAYBOOK.read_text(encoding="utf-8"))
    except Exception:
        return "SELF-LEARNING DATA: not ready yet; make an original topic and an immediate curiosity gap."

    if not isinstance(data, dict) or not data.get("learning_ready"):
        return "SELF-LEARNING DATA: warming up; prioritize originality, a strong first 3 seconds, clear escalation and a satisfying payoff."

    winners = _evidence_rows(data.get("winning_patterns", []), 10)
    weak = _evidence_rows(data.get("weak_patterns", []), 8)

    lines = [
        "SELF-LEARNING CHANNEL PLAYBOOK — CREATIVE V3",
        f"Published videos analyzed: {data.get('video_count', 0)}",
        "Objective: maximize retention, shares and subscriber conversion without sacrificing originality.",
        "",
        "HOW TO USE LEARNING:",
        "- Treat repeated winning patterns as guidance, not a template to copy.",
        "- Use at most 1–2 winning creative patterns in this Short so experiments stay interpretable.",
        "- Keep the topic, wording, example and visuals original even when the structure is learned.",
        "- If no pattern clearly fits the topic, ignore it and prioritize story quality.",
        "",
        "REPEATED WINNING CREATIVE PATTERNS (n>=2):",
    ]
    if winners:
        for score, n, pattern in winners:
            lines.append(f"- {pattern} | learned score={score:.2f} | evidence n={n}")
    else:
        lines.append("- No repeated winner yet; explore deliberately.")

    lines += ["", "REPEATED WEAK PATTERNS TO AVOID WHEN THEY FIT THE SAME KIND OF STORY (n>=2):"]
    if weak:
        for score, n, pattern in weak:
            lines.append(f"- {pattern} | learned score={score:.2f} | evidence n={n}")
    else:
        lines.append("- No repeated weak pattern yet.")

    lines += [
        "",
        "STORY QUALITY PRIORITIES:",
        "- Hook immediately with an observable surprise, contradiction or curiosity gap; no warm-up.",
        "- Escalate the mystery before explaining it.",
        "- Explain one clear mechanism using a concrete everyday example.",
        "- Reframe what the viewer thought was happening before the strongest payoff.",
        "- End the current topic cleanly; never sacrifice the payoff to fit a learned pattern.",
        "- Keep narration conversational and easy to follow when visuals are only supporting atmosphere.",
        "",
        "RECENT WINNING TOPICS (DO NOT REUSE):",
        *[f"- {x}" for x in data.get("winning_topics", [])[:8] if x],
        "",
        "EXPERIMENT RULE:",
        "Preserve controlled exploration: most Shorts can use proven patterns, some should test adjacent structures, and a smaller share should try genuinely new approaches.",
    ]
    return "\n".join(lines)[:max_chars]

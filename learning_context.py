"""Build compact, evidence-weighted creative learning context for Gemini."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLAYBOOK = ROOT / "analytics" / "playbook.json"


def _rows(rows, limit=8, minimum=2):
    result = []
    for row in rows or []:
        try:
            n = int(row.get("sample_size", 0) or 0)
            score = float(row.get("score", 0) or 0)
        except (TypeError, ValueError):
            continue
        pattern = str(row.get("pattern", "")).strip()
        if pattern and n >= minimum:
            result.append((score, n, pattern))
    result.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return result[:limit]


def load_learning_context(max_chars: int = 7000) -> str:
    try:
        data = json.loads(PLAYBOOK.read_text(encoding="utf-8"))
    except Exception:
        return "SELF-LEARNING DATA: not ready yet; prioritize originality and a strong first 3 seconds."

    if not isinstance(data, dict) or not data.get("learning_ready"):
        return "SELF-LEARNING DATA: warming up; prioritize originality, immediate curiosity, escalation and a satisfying payoff."

    combinations = _rows(data.get("winning_combinations", []), 5)
    pairs = _rows(data.get("winning_hook_payoff_pairs", []), 4)
    winners = _rows(data.get("winning_patterns", []), 8)
    weak = _rows(data.get("weak_patterns", []), 6)

    lines = [
        "SELF-LEARNING CHANNEL PLAYBOOK — CREATIVE V3",
        f"Published videos analyzed: {data.get('video_count', 0)}",
        "Objective: maximize retention, shares and subscriber conversion without sacrificing originality.",
        "",
        "HOW TO APPLY LEARNING:",
        "- Prefer ONE repeated winning combination when it naturally fits the topic.",
        "- Never copy a winning topic, sentence, example, or visual concept.",
        "- Keep the topic original and make the learned structure serve the story.",
        "- If the learned combination conflicts with story quality, ignore it.",
        "- Do not force a pattern merely because it has a high score.",
        "",
        "REPEATED WINNING COMBINATIONS (n>=2):",
    ]
    if combinations:
        lines.extend(f"- {pattern} | score={score:.2f} | evidence n={n}" for score, n, pattern in combinations)
    else:
        lines.append("- No repeated combination has enough evidence yet; explore.")

    lines += ["", "REPEATED WINNING HOOK + PAYOFF PAIRS (n>=2):"]
    if pairs:
        lines.extend(f"- {pattern} | score={score:.2f} | evidence n={n}" for score, n, pattern in pairs)
    else:
        lines.append("- No repeated hook/payoff pair has enough evidence yet.")

    lines += ["", "STRONG INDIVIDUAL PATTERNS (secondary guidance):"]
    if winners:
        lines.extend(f"- {pattern} | score={score:.2f} | n={n}" for score, n, pattern in winners)
    else:
        lines.append("- None yet.")

    lines += ["", "REPEATED WEAK PATTERNS TO AVOID WHEN RELEVANT (n>=2):"]
    if weak:
        lines.extend(f"- {pattern} | score={score:.2f} | n={n}" for score, n, pattern in weak)
    else:
        lines.append("- None yet.")

    lines += [
        "",
        "STORY QUALITY PRIORITIES:",
        "- Hook immediately with an observable surprise, contradiction or curiosity gap; no warm-up.",
        "- Escalate the mystery before explaining it.",
        "- Explain one clear mechanism with a concrete everyday example.",
        "- Reframe what the viewer thought was happening before the strongest payoff.",
        "- Finish the current topic cleanly; never sacrifice the payoff to fit a learned pattern.",
        "- Keep narration conversational and understandable even if visuals are only supporting atmosphere.",
        "",
        "RECENT WINNING TOPICS (DO NOT REUSE):",
        *[f"- {x}" for x in data.get("winning_topics", [])[:8] if x],
        "",
        "EXPERIMENT RULE:",
        "Maintain controlled exploration: mostly proven combinations, some adjacent variations, and a smaller share of genuinely new structures.",
    ]
    return "\n".join(lines)[:max_chars]

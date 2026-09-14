"""Story-only topic-to-stock-media lock.

Loaded after story_stock_runtime. Publish Shorts never imports this module.
Every Story Short gets a stable visual domain from its subject/topic, and every
scene search is anchored to that domain so narration details cannot drift the
stock footage into unrelated imagery.
"""
from __future__ import annotations

import re
import stock_search


PROFILE_RULES = [
    (r"viswanathan\s+anand|vishwanathan\s+anand|\banand\b.*chess|chess.*\banand\b", ["chess", "chess player", "chess board", "chess match", "chess tournament"]),
    (r"mary\s+kom|mary\s+kom|\bkom\b.*boxing|boxing.*\bkom\b", ["boxing", "boxer", "boxing ring", "boxing training", "boxing match"]),
    (r"muhammad\s+ali|mike\s+tyson|floyd\s+mayweather", ["boxing", "boxer", "boxing ring", "boxing training", "boxing match"]),
    (r"neeraj\s+chopra", ["javelin", "javelin throw", "athlete training", "track and field"]),
    (r"sachin\s+tendulkar|virat\s+kohli|ms\s+dhoni", ["cricket", "cricket player", "cricket bat", "cricket match", "cricket training"]),
    (r"michael\s+jordan|lebron\s+james|kobe\s+bryant|stephen\s+curry", ["basketball", "basketball player", "basketball court", "basketball training"]),
    (r"arunima\s+sinha|tenzing\s+norgay|edmund\s+hillary", ["mountaineering", "mountain climber", "mountain expedition", "himalayan mountains"]),
    (r"nadia\s+comaneci", ["gymnastics", "gymnast", "balance beam", "gymnastics training", "gymnastics competition"]),
    (r"milkha\s+singh|usain\s+bolt", ["sprinting", "sprinter", "track athlete", "running track", "track and field"]),
    (r"p\.j\.\s+abdul\s+kalam|apj\s+abdul\s+kalam|abdul\s+kalam", ["aerospace", "rocket scientist", "space program", "scientist laboratory", "rocket launch"]),
    (r"thomas\s+edison|nikola\s+tesla|marie\s+curie|albert\s+einstein|stephen\s+hawking", ["science laboratory", "scientist", "scientist working", "research laboratory", "scientific experiment"]),
    (r"walt\s+disney|steve\s+jobs|bill\s+gates|elon\s+musk|d?hirubhai\s+ambani|dheerubhai\s+ambani", ["entrepreneur", "business meeting", "company office", "business planning", "startup"]),
    (r"j\.k\.\s+rowling|jk\s+rowling|william\s+shakespeare", ["writer", "writing desk", "author writing", "manuscript", "books"]),
    (r"oprah\s+winfrey|amitabh\s+bachchan|tom\s+hanks", ["television studio", "actor", "film set", "stage performance", "entertainment"]),
]

GENERIC_RULES = [
    (r"chess|grandmaster|checkmate|chessboard|chess tournament", ["chess", "chess player", "chess board", "chess match"]),
    (r"boxing|boxer|boxing ring|knockout|heavyweight", ["boxing", "boxer", "boxing ring", "boxing training"]),
    (r"cricket|wicket|bowler|batsman|batter|ipl", ["cricket", "cricket player", "cricket match", "cricket training"]),
    (r"gymnast|gymnastics|beam|uneven bars", ["gymnastics", "gymnast", "gymnastics training", "gymnastics competition"]),
    (r"football|soccer|goalkeeper|pitch", ["soccer", "soccer player", "soccer match", "soccer training"]),
    (r"tennis|wimbledon|racket", ["tennis", "tennis player", "tennis match", "tennis training"]),
    (r"swimmer|swimming|pool|freestyle", ["swimming", "swimmer", "competitive swimming", "swimming pool"]),
    (r"mountain|climbing|climber|everest|himalaya", ["mountaineering", "mountain climber", "mountain expedition", "himalayan mountains"]),
    (r"invent|invention|laboratory|scientist|research|experiment", ["scientist", "research laboratory", "inventor workshop", "scientific experiment"]),
    (r"music|singer|concert|piano|guitar", ["music performance", "musician", "concert", "music rehearsal"]),
    (r"actor|actress|film|movie|cinema|stage", ["actor", "film set", "movie production", "stage performance"]),
    (r"entrepreneur|business|company|startup|factory", ["entrepreneur", "business meeting", "company office", "factory"]),
]


def _topic_text(script: dict) -> str:
    parts = [script.get("story_person"), script.get("topic"), script.get("title"), script.get("interactive_pillar")]
    for scene in script.get("scene_plan") or []:
        if isinstance(scene, dict):
            parts.append(scene.get("narration"))
    return " ".join(str(x or "") for x in parts).lower()


def _profile(script: dict) -> list[str]:
    text = _topic_text(script)
    person = str(script.get("story_person") or "").lower()
    for pattern, phrases in PROFILE_RULES:
        if re.search(pattern, person, re.I) or re.search(pattern, text, re.I):
            return phrases
    for pattern, phrases in GENERIC_RULES:
        if re.search(pattern, text, re.I):
            return phrases
    return ["historical person", "real person"]


_original_context = getattr(stock_search, "_story_context", None)


def _locked_context(script: dict, scene_no: int) -> list[str]:
    profile = _profile(script)
    result = list(profile)
    # Keep scene-specific context only when it does not replace the stable topic.
    if _original_context:
        try:
            for phrase in _original_context(script, scene_no):
                if phrase not in result and len(result) < 7:
                    result.append(phrase)
        except Exception:
            pass
    return result[:7]


if _original_context is not None:
    stock_search._story_context = _locked_context

print("🎯 STORY TOPIC MEDIA LOCK: subject-specific stock domain enforced")

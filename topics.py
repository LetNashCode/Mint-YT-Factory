"""
Topic bank for the channel. main.py picks the next unused topic each run
and records it in used_topics.json so the same topic never repeats.

Add/remove categories freely — the script generator will invent specific
Top-5 items within whichever category is chosen.
"""
import json
import os
import random

TOPIC_BANK = [

# Mysteries
"the village that disappeared overnight",
"the signal from space scientists still cannot explain",
"the mystery of the Dyatlov Pass incident",
"the strange disappearance of the Roanoke colony",
"the mystery behind the Bermuda Triangle",
"the unexplained WOW signal",
"the mysterious Black Knight satellite",
"the world's most mysterious island",
"the man who disappeared from a locked room",
"the biggest unsolved mystery in history",

# History
"the richest man who ever lived",
"how one mistake changed history forever",
"the world's shortest war",
"the emperor who disappeared without a trace",
"the lost city nobody has found",
"the world's oldest civilization",
"the real story behind the Titanic",
"the deadliest day in human history",
"the largest empire ever built",
"the greatest military strategy ever used",

# Space
"what would happen if Earth stopped spinning",
"the coldest place in the universe",
"the loudest sound ever recorded",
"the largest black hole ever discovered",
"the biggest planet ever found",
"what happens inside a black hole",
"could humans survive on Mars",
"the scariest planet discovered",
"the fastest thing in the universe",
"what if the Moon disappeared",

# Science
"why airplanes never fall from the sky",
"what happens when lightning hits a person",
"what would happen if oxygen disappeared",
"why time moves differently in space",
"how your brain tricks you every day",
"why we dream",
"how memory actually works",
"what happens after you die scientifically",
"the strongest material on Earth",
"the world's deadliest bacteria",

# Human Body
"the rarest disease ever recorded",
"why humans get goosebumps",
"what happens if you never sleep",
"why your heart never gets tired",
"the strongest muscle in your body",
"the science behind fear",
"how adrenaline saves lives",
"what happens inside your brain during fear",
"the world's rarest blood type",
"the longest someone survived without food",

# Business
"how Apple almost went bankrupt",
"how Netflix defeated Blockbuster",
"the biggest business mistake ever made",
"how one man built Amazon",
"the rise of Nvidia",
"how Ferrari became famous",
"the Coca-Cola secret",
"the story behind McDonald's",
"why Rolex is so expensive",
"how LEGO survived bankruptcy",

# Internet
"the darkest mystery on the internet",
"the biggest internet mystery ever",
"the story behind Cicada 3301",
"the world's most mysterious website",
"the strangest Reddit mystery",
"the lost media nobody found",
"the hacker nobody caught",
"the biggest crypto mystery",
"the world's oldest website",
"the biggest YouTube mystery",

# Animals
"the smartest animal on Earth",
"the deadliest animal you've never heard of",
"animals that should not exist",
"the deepest living creature",
"the immortal jellyfish",
"how octopuses escape everything",
"the world's strongest insect",
"the fastest bird alive",
"the largest snake ever recorded",
"animals with superpowers"

]

USED_TOPICS_PATH = os.path.join(os.path.dirname(__file__), "used_topics.json")


def _load_used():
    if os.path.exists(USED_TOPICS_PATH):
        with open(USED_TOPICS_PATH, "r") as f:
            return json.load(f)
    return []


def _save_used(used):
    with open(USED_TOPICS_PATH, "w") as f:
        json.dump(used, f, indent=2)


def get_next_topic() -> str:
    """Return a topic not used recently. Resets once the bank is exhausted."""
    used = _load_used()
    available = [t for t in TOPIC_BANK if t not in used]
    if not available:
        used = []
        available = TOPIC_BANK[:]
    topic = random.choice(available)
    used.append(topic)
    _save_used(used)
    return topic

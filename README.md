# Mint-YT-Factory

Automated production pipeline for entertaining YouTube Shorts.

## Channel format

The channel focuses on **everyday curiosities** — things people see, use, hear, taste, or experience in normal life but rarely stop to ask about.

Examples:

- Why does your voice sound weird in a recording
- Why does toothpaste make orange juice taste disgusting
- Why does a fan make you feel cooler
- Why does your phone get hot while charging
- Why does a mirror seem to reverse left and right

Science is the explanation, not the packaging. Topics must be simple, relatable, visual, and genuinely explainable.

## Active production pipeline

```text
Everyday topic
      ↓
Gemini entertainment writer
      ↓
Gemini visual director
      ↓
Locked 7-scene story / 14 visual beats
      ↓
Gemini Visual/Search Director
      ↓
Pexels video → Pexels photo fallback
      ↓
Deterministic metadata selection
      ↓
TikTok TTS narration
      ↓
Whisper word timing + narration-aware captions
      ↓
MoviePy assembly
      ↓
Final validation
      ↓
YouTube upload + engagement experiment
```

### Media rules

- Pexels is the **only production media provider**.
- Gemini is used as the **Visual/Search Director**, not as a candidate-media verifier.
- Candidate Pexels images/videos are **never uploaded to Gemini for visual verification**.
- AI image generation is disabled in production.
- Unrelated-media fallback is forbidden; if no relevant Pexels asset can be found, production stops.
- Each Short requires exactly **7 scenes × 2 assets = 14 assets**.
- Scene 2 shots must advance the same story rather than repeat the first shot.

The active implementation is in `pexels_media.py` and is installed by `production_entry.py`.

## Script goals

- One story, not a countdown or list
- Immediate curiosity hook
- Simple spoken English
- Quirky, entertaining narration
- Clear visual progression
- Satisfying payoff
- No unnecessary scientific jargon
- Scene 7 resolves the current story before the locked continuation teaser
- The YouTube description describes **only the current Short**

## Captions and video quality

Whisper provides word timing and the verified narration remains the source of truth. The caption layer uses a safe on-screen lane and one timed word at a time so captions do not merge into malformed strings.

Production output is portrait 2160×3840 at 60 FPS with H.264 encoding, 68 Mbps video bitrate and 384 kbps AAC audio.

## Research status

The repository contains a research/claim-verification subsystem, but the current production entrypoint does **not** run that subsystem before script generation. `config.yaml` therefore keeps research explicitly disabled rather than falsely advertising a research-first production gate.

If research-first publishing is re-enabled later, it should be wired into `main.run()` and made a hard pre-script/pre-publish gate rather than only changing a configuration flag.

## Self-learning

The factory refreshes YouTube analytics and maintains a learning playbook. It uses a 70% proven-pattern / 20% adjacent-experiment / 10% wild-experiment strategy, while protecting against duplicate and near-duplicate topics.

Engagement experiments are sequential and are counted only when the planned creator comment is confirmed as delivered.

## Project structure

```text
.
├── .github/workflows/publish.yml
├── assets/
├── analytics/
├── assemble.py
├── config.yaml
├── generate_images.py          # compatibility wrapper → pexels_media.py
├── generate_script.py
├── main.py
├── music.py
├── pexels_media.py
├── production_entry.py
├── quality_overrides.py
├── research.py
├── research/
├── runtime_overrides.py
├── sitecustomize.py
├── topics.py
├── tts.py
├── upload_youtube.py
├── used_topics.json
├── validate_video.py
└── requirements.txt
```

## GitHub Actions

There is one production workflow:

`.github/workflows/publish.yml`

It installs the required dependencies, verifies the runtime, runs `production_entry.py`, uploads the finished Short, and safely synchronizes topic state.

## Required secrets

```text
GEMINI_API_KEY
PEXELS_API_KEY
YOUTUBE_TOKEN_JSON
```

## Run locally

```bash
python production_entry.py
```

The same production entrypoint is used by GitHub Actions.

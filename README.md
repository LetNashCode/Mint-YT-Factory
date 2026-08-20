# Mint-YT-Factory

Automated production pipeline for research-backed YouTube Shorts.

## Channel format

The channel focuses on **everyday curiosities** — things people see, use, hear, taste, or experience in normal life but rarely stop to ask about.

Examples:

- Why does your voice sound weird in a recording
- Why does toothpaste make orange juice taste disgusting
- Why does a fan make you feel cooler
- Why does your phone get hot while charging
- Why does a mirror seem to reverse left and right

Science is the explanation, not the packaging. Topics must be simple, relatable, visual, and genuinely researchable.

## Production pipeline

```text
Everyday topic
      ↓
Verified scientific research
      ↓
Research-backed story script
      ↓
Claim verification + publishing safety gate
      ↓
TikTok TTS narration
      ↓
14 AI-generated visuals
      ↓
Whisper word timing + narration-aware caption repair
      ↓
MoviePy assembly
      ↓
YouTube upload
```

## Research safety

The pipeline does not publish merely because an LLM says a claim is true. Research discovery, source relevance, evidence retrieval, DOI verification, claim verification, and the final publishing gate remain separate checks.

Everyday wording is translated internally into scientific vocabulary for scholarly discovery. That vocabulary is never used as public narration.

## Script goals

- One story, not a countdown or list
- Immediate curiosity hook
- Simple spoken English
- Quirky, entertaining narration
- Clear visual progression
- A satisfying explanation without unnecessary jargon
- Strong ending/open loop
- Current-topic identity checks
- Next-topic continuation checks
- Public description describes only the current Short

## Captions

Whisper provides timing, but the verified narration saved for the run is the authoritative wording. The caption layer also enforces a minimum separation between words so overlapping text cannot visually merge into malformed strings.

## Project structure

```text
.
├── .github/workflows/publish.yml
├── assets/
│   ├── Fonts/Poppins-ExtraBold.ttf
│   └── music/
├── assemble.py
├── config.yaml
├── generate_images.py
├── generate_script.py
├── generate_script/__init__.py
├── main.py
├── music.py
├── research.py
├── research/__init__.py
├── topics.py
├── topics/__init__.py
├── tts.py
├── upload_youtube.py
├── used_topics.json
├── verify_claims.py
├── whisper_align.py
├── requirements.txt
└── README.md
```

## GitHub Actions

There is intentionally **one production workflow**:

`.github/workflows/publish.yml`

It installs the required system/Python dependencies, verifies the runtime, runs `main.py`, and publishes the completed Short.

The old one-time FFmpeg/bootstrap workflows are not part of the production system.

## Required secrets

```text
GEMINI_API_KEY
YOUTUBE_TOKEN_JSON
```

## Run locally

```bash
python main.py
```

The same production pipeline is used locally and by GitHub Actions.

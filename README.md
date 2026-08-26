# Mint-YT-Factory

Automated production pipeline for entertaining YouTube Shorts.

## Production architecture

```text
Everyday topic
  -> Gemini Entertainment Writer
  -> Gemini Story Visual Director
  -> locked 7-scene / 14-beat storyboard
  -> Gemini Visual/Search Director
  -> Pexels video candidates
  -> Gemini Visual Verifier
  -> Pixabay video candidates if needed
  -> Gemini Visual Verifier
  -> Pexels photo candidates if needed
  -> Gemini Visual Verifier
  -> Pixabay photo candidates if needed
  -> Gemini Visual Verifier
  -> deterministic relevance + diversity selection
  -> TikTok TTS
  -> Whisper captions
  -> music + story-aware SFX
  -> MoviePy assembly
  -> validation
  -> YouTube upload + creator comment experiment
  -> analytics + learning
```

Gemini has four separate jobs: write the entertaining narration, translate the locked narration into literal visuals, create concrete stock-media search queries, and finally inspect a small candidate pool to verify that the actual media visibly supports the spoken beat. Gemini never generates replacement visuals.

The production media providers are **Pexels and Pixabay only**. Provider priority is Pexels VIDEO → Pixabay VIDEO → Pexels PHOTO → Pixabay PHOTO. For each shot, the top metadata candidates are inspected by Gemini; a candidate must reach the configured visual-verification threshold before it can be used. If neither stock provider can supply a sufficiently relevant asset, production stops. There is no AI-image fallback, Pollinations/FLUX fallback, generic stock filler, or unrelated-media fallback.

Each Short is exactly 7 scenes × 2 unique assets. Visuals must directly support the spoken beat and advance the story.

## Engagement learning

The factory can automatically post one topic-specific creator comment. Pinning remains manual because the standard YouTube Data API does not expose a supported pin-comment operation. Experiments are sequential: prediction, choice, challenge, disagreement, next_experiment, curiosity. An experiment counts only after creator-comment delivery is confirmed. Learning uses comments, shares and available retention/subscriber metrics.

## Analytics

Basic YouTube statistics are refreshed every run. Advanced YouTube Analytics metrics are retried and used when the OAuth token has the required Analytics scope. If the Analytics API is unavailable, the durable registry remains intact and the system explicitly reports that advanced metrics were not refreshed.

## Research

A research subsystem exists but is intentionally disabled in the active entertainment-first pipeline.

## Output

Portrait 2160×3840, 60 FPS, H.264, 68 Mbps video, 384 kbps AAC, narration-authoritative Whisper captions.

## Required secrets

```text
GEMINI_API_KEY
PEXELS_API_KEY
PIXABAY_API_KEY
YOUTUBE_TOKEN_JSON
```

## Run

```bash
python production_entry.py
```

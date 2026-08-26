# Mint-YT-Factory

Automated production pipeline for entertaining YouTube Shorts.

## Production architecture

```text
Everyday topic
  -> Gemini Entertainment Writer
  -> Gemini Story Visual Director
  -> locked 7-scene / 14-beat storyboard
  -> Gemini Visual/Search Director
  -> Pexels video/photo
  -> deterministic relevance + diversity selection
  -> TikTok TTS
  -> Whisper captions
  -> music + story-aware SFX
  -> MoviePy assembly
  -> validation
  -> YouTube upload + creator comment experiment
  -> analytics + learning
```

Gemini has three separate jobs: write the entertaining narration, translate the locked narration into literal visuals, and create concrete Pexels search queries. Gemini does not inspect returned Pexels candidates. Pexels is the only production media provider; AI image generation and unrelated-media fallbacks are disabled.

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
YOUTUBE_TOKEN_JSON
```

## Run

```bash
python production_entry.py
```

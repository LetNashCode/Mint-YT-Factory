# Mint-YT-Factory

Automated production pipeline for entertaining YouTube Shorts.

## Production architecture

```text
Everyday topic → Gemini Entertainment Writer → Gemini Story Visual Director
→ Gemini Visual/Search Director → Pexels video/photo → deterministic selection
→ TikTok TTS → Whisper captions → music/SFX → MoviePy → validation
→ YouTube upload + creator comment experiment → analytics → learning
```

### Gemini roles

1. **Entertainment Writer** — writes only the spoken story; playful, conversational, curiosity-driven and not constrained by stock footage.
2. **Story Visual Director** — converts the locked narration into two literal, story-advancing shots per scene.
3. **Visual/Search Director** — converts each shot into concrete Pexels queries and a casting brief.

Gemini does **not** inspect returned Pexels candidates. Candidate-media verification is intentionally disabled.

## Media rules

- Pexels is the only production media provider.
- AI image generation is disabled in production.
- Pollinations/FLUX are not production fallbacks.
- Exactly 7 scenes × 2 unique assets = 14 assets.
- No unrelated fallback media.
- Visuals must directly support the spoken beat and advance the story.

## Engagement learning

The factory can automatically post one topic-specific creator comment after upload. Pinning remains manual because the standard YouTube Data API does not expose a supported pin-comment operation.

Experiments are sequential: prediction, choice, challenge, disagreement, next_experiment, curiosity. The learning engine counts an experiment only when the creator comment is confirmed as delivered and learns from comments, shares and available retention/subscriber metrics.

## Analytics

Basic YouTube statistics are refreshed every run. Advanced YouTube Analytics metrics are retried and used when the OAuth token has the required Analytics scope. If the Analytics API is unavailable, the durable registry remains intact and the system does not pretend advanced metrics were refreshed.

## Research

A research subsystem exists but is intentionally disabled in the active entertainment-first pipeline. Re-enabling it should be an explicit production architecture decision, not merely a configuration change.

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

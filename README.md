# Mint-YT-Factory

Automated production pipeline for entertaining YouTube Shorts.

## Final production architecture

```text
Everyday topic
      ↓
Gemini Entertainment Writer
      ↓
Gemini Story Visual Director
      ↓
Locked 7-scene story / 14 visual beats
      ↓
Gemini Visual/Search Director
      ↓
Pexels video → Pexels photo fallback
      ↓
Deterministic relevance + diversity selection
      ↓
TikTok TTS narration
      ↓
Whisper word timing + narration-aware captions
      ↓
Music + story-aware SFX
      ↓
MoviePy assembly
      ↓
Final validation
      ↓
YouTube upload + creator engagement experiment
      ↓
YouTube analytics → learning engine
```

## Gemini responsibilities

### 1. Entertainment Writer
Gemini writes the spoken story only. It is deliberately not constrained by stock-media search limitations. The target is conversational, playful, quirky, curiosity-driven narration with a clear escalation and satisfying payoff.

### 2. Story Visual Director
A second Gemini pass receives the locked narration and creates two literal, story-advancing visual beats per scene. It translates metaphors into observable physical scenes instead of creating abstract science imagery.

### 3. Visual/Search Director
A third Gemini pass receives each visual beat and creates concrete Pexels search queries plus a casting brief. It does **not** inspect Pexels candidates.

## Media rules

- Pexels is the only production media provider.
- Gemini directs the search; Pexels supplies the actual media.
- Gemini candidate-media verification is intentionally disabled.
- Candidate Pexels images/videos are never uploaded to Gemini for verification.
- AI image generation is disabled in production.
- Unrelated-media fallback is forbidden; if no acceptable Pexels asset can be selected, production stops.
- Each Short requires exactly 7 scenes × 2 assets = 14 assets.
- Shot 1 establishes the physical situation; Shot 2 advances it.
- Selection combines Gemini search intent with deterministic metadata relevance, action matching, portrait suitability, duration and duplicate protection.

## Script goals

- One connected story, not a list
- Immediate curiosity hook
- Simple spoken English
- Quirky, entertaining narration
- Clear visual progression
- Satisfying payoff
- No unnecessary scientific jargon
- Scene 7 resolves the current story
- The locked continuation topic is spoken only as the final continuation tease
- YouTube descriptions describe only the current Short

## Engagement learning

After upload, the factory can automatically post one topic-specific creator comment. Pinning remains manual because the standard YouTube Data API does not provide a supported pin-comment operation.

Engagement experiments are tested sequentially:

1. prediction
2. choice
3. challenge
4. disagreement
5. next_experiment
6. curiosity

The learning engine only counts an experiment when the creator comment is confirmed as delivered. It learns from comments, shares and other available YouTube Analytics metrics and favors the best-performing mechanic once enough data exists.

## Analytics

The factory maintains a durable video registry and snapshots. Basic YouTube Data API statistics are refreshed every production run. Advanced YouTube Analytics metrics are collected when the OAuth token has the required `yt-analytics.readonly` access; if the Analytics API is temporarily unavailable, production continues without pretending those advanced metrics were refreshed.

## Research status

A research/claim-verification subsystem exists in the repository but is intentionally **not part of the active production gate**. The channel currently prioritizes entertainment-first everyday curiosity stories. Re-enabling research should be a deliberate architecture change, not a configuration-only switch.

## Captions and video quality

Whisper provides word timing and the verified narration remains the source of truth. Captions use a safe on-screen lane and one timed word at a time.

Production output is portrait 2160×3840 at 60 FPS with H.264 encoding, 68 Mbps video bitrate and 384 kbps AAC audio.

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

# Mint-YT-Factory — AI Project Memory

## Purpose
This is durable repository memory for future AI agents. Read it before changing either pipeline. Preserve the contracts below unless an explicit migration is requested.

Last consolidated: 2026-09-02.

## Current architecture
Two separate pipelines:
- Publish Shorts: `production_entry.py` → `main.py`
- Interactive Mystery: `interactive_main.py` → `generate_script/interactive.py`

Core flow:
Topic → script → quality gates → canonical next-topic lock → TTS → duration guard → stock media → visual verification → music/SFX → MoviePy assembly → encoded-duration verification → quality validation → YouTube upload → topic commit → analytics/learning.

## Visual contract
- Exactly 7 scenes.
- Exactly 2 visual beats/assets per scene (14 total).
- Stock media only: Pexels VIDEO → Pixabay VIDEO → Pexels PHOTO → Pixabay PHOTO.
- No unrelated-media fallback.
- Visuals must visibly support narration.

## Major fixes implemented

### 1. Narration-authoritative ending
Problem: visual/music tails could outlive narration; an earlier implementation also referenced an undefined `_assert_output_matches_narration`.
Fix: `assemble.py` trims timeline layers to narration-authoritative duration and reopens the encoded output to verify duration.
Do not regress: never remove encoded-output duration verification.

### 2. Upload bookkeeping crash
Problem: Interactive workflow uploaded successfully then crashed with `NameError: vid is not defined`.
Rule: use the authoritative returned YouTube video ID and do not let optional comment/analytics failures invalidate a successful upload.

### 3. Next-topic continuation
Problems: missing, paraphrased, duplicated, abrupt, or leaked next topic.
Current `main.py` design:
1. Generate current-topic story first.
2. Treat `next_short.topic` as metadata.
3. Repair invalid/missing metadata through topic engine.
4. Reserve one canonical next topic.
5. Append deterministic bridge containing exact topic.
6. Save continuation state.
7. Commit topic state only after successful upload.

Key functions: `_lock_canonical_topic`, `reserve_next_short`, `lock_next_topic`, `_generate_natural_bridge`, `save_next_short`, `commit_topic`.

Important: current code uses deterministic bridge insertion. `production_entry.py` has an older log string saying continuation is Gemini-authored; keep logs and code consistent when editing.

### 4. Description contamination
Requirement: YouTube description describes only the current Short.
Current implementation: `build_youtube_metadata()` uses current `script["topic"]` only.
Do not put `next_short.topic` in title/description/tags unless explicitly requested.

### 5. Duplicate-topic prevention
State model:
- Used topics come from history.
- Reserved/pending next topics are separate.
- Duplicate validation occurs before canonical locking.
- Next topic is reserved before production proceeds.
- Current topic is committed only after successful upload.
Relevant functions: `get_next_topic`, `reserve_next_short`, `save_next_short`, `commit_topic`, `validate_topic_for_pipeline`, `_read_used`, `_generate_topic`.
If duplicates recur, inspect persistence files and reservation/commit ordering before changing prompts.

### 6. Gemini 503/429 resilience
`main.py` detects transient failures and retries them without consuming normal script attempts. Retries are bounded.
Do not create infinite retry loops.

### 7. Qwen fallback lessons
Observed failures: wrong scene count, no scene list, invalid/non-JSON output.
Any fallback must parse defensively, preserve current topic, satisfy exactly 7 scenes and pass quality gates. Avoid repeatedly loading heavyweight models in one run.

### 8. Runtime problem lessons
Runs became close to one hour because of repeated Gemini calls, strict visual-gate rejections, repeated Qwen loading, and 503/429 waits.
Do not solve this by increasing retries. Measure stages and repair weak outputs where possible.

### 9. Interactive Mystery
Keep independent from Publish Shorts. Narration is master clock; trim all layers to narration; verify encoded output; preserve 7-scene/14-visual contract.

### 10. Quality gate
Production checks resolution 2160×3840, 60 FPS, H.264, bitrate floor, final duration, and narration alignment. Do not bypass validation merely to finish faster.

## Files to inspect first
Publish Shorts:
- `production_entry.py`
- `main.py`
- `topics.py`
- `topic_history.py`
- `generate_script/entertainment.py`
- `story_quality_gate.py`
- `quality_overrides.py`
- `runtime_overrides.py`
- `stock_media_resilient.py`
- `assemble.py`
- `tts.py`
- `upload_youtube.py`
- `validate_video.py`

Interactive Mystery:
- `interactive_main.py`
- `interactive_topics.py`
- `interactive_analytics.py`
- `generate_script/interactive.py`

Automation: `.github/workflows/`.

## Non-negotiable contracts
- 7 scenes and 14 visuals.
- Entertaining coherent current-topic story.
- No unrelated stock fallback.
- Narration is master timing clock.
- No silent visual tail.
- Current topic and next topic remain separate.
- Description describes current topic only.
- Next topic is canonical and state-managed.
- Topic/history state changes after successful upload.
- Successful upload is not marked failed because optional post-upload actions fail.
- Publish and Interactive pipelines remain independently testable.
- Retries are bounded.

## Known cleanup targets
1. `production_entry.py` continuation log wording is stale versus deterministic bridge code.
2. README may be stale; verify against runtime code.
3. Qwen fallback startup/reload cost needs monitoring.
4. “No searchable physical action/state” gate caused excessive rejections; improve search-query/visual-beat repair instead of endless regeneration.
5. Creator comments previously failed with HTTP 403 insufficient OAuth scopes; upload still succeeded. This is auth configuration, not video generation.

## Future AI workflow
1. Read this file.
2. Inspect relevant entrypoint.
3. Trace data flow and source of truth.
4. Make minimal changes.
5. Run syntax/import checks.
6. Check workflow logs after deployment.
7. Append problem, root cause, fix, files changed, validation, and regression rule to this file.

## Current status
Implemented: separate pipelines, 7-scene/14-visual contract, stock-provider priority, visual verification, narration-authoritative assembly, encoded-duration verification, final quality validation, authoritative upload IDs, current-topic-only descriptions, canonical next-topic locking, topic reservation/commit architecture, bounded transient retries, analytics/learning, and engagement experiments that should not invalidate upload success.

Continue monitoring: duplicate-topic prevention in real state, Gemini quota behavior, Qwen reliability/runtime, visual-gate rejection rate, creator-comment OAuth scopes, and consistency between code/README/startup logs.

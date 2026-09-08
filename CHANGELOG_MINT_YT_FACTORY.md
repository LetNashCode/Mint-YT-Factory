# Mint-YT-Factory Change Log

This file is the persistent project change history and implementation context.

## 2026-08-27 — Gemini model policy + stock-media pipeline

### User requirement
- Use **only `gemini-flash-lite-latest`** for Gemini operations in the project.
- Do not switch to another Gemini model when the primary model is unavailable.
- Retry the same canonical model instead.

### Changes made
- `stock_search.py`
  - Removed `GEMINI_FALLBACK_MODEL`.
  - `_gemini()` now uses only `gemini-flash-lite-latest`.
  - Temporary Gemini failures retry the same model up to 3 attempts.
  - Stock-search logs now explicitly report that there is no fallback model.
  - Visual verification now uses only `gemini-flash-lite-latest`.
  - Visual verification retries the same model up to 3 attempts.
  - Removed all fallback-model execution paths.
- `stock_media_resilient.py`
  - Removed the metadata-only verification override.
  - Stock media generation now uses the `stock_search.py` Gemini search + visual verification pipeline.
  - Logs explicitly identify `gemini-flash-lite-latest` as the only Gemini model.

### Important current behavior
- Gemini model: `gemini-flash-lite-latest` ONLY.
- Pexels/Pixabay remain the stock-media providers.
- Provider fallback is allowed; Gemini model fallback is not.

### Previous issue that triggered this change
GitHub Actions failed because the code attempted to fall back from `gemini-flash-lite-latest` to `gemini-2.5-flash-lite`, and the API reported that `gemini-2.5-flash-lite` was no longer available to new users.

---

## 2026-08-27 — Media provider restriction

### User requirement
- **Pexels and Pixabay are the only permitted media providers for videos and images.**
- Do not use any other stock-media, image, video, search, or media provider for production assets.
- This restriction applies to both video and image assets throughout the Mint-YT-Factory pipeline.

### Implementation constraint
- Gemini may be used only for reasoning/search direction/visual analysis as already specified; it is **not** a media provider.
- Production media retrieval must remain limited to:
  1. Pexels VIDEO
  2. Pixabay VIDEO
  3. Pexels PHOTO
  4. Pixabay PHOTO
- If a Pexels/Pixabay asset cannot be found or verified, the system must not silently substitute media from another provider.

---

## 2026-08-27 — Gemini fallback removal hardening

### User requirement
- Continue using **only `gemini-flash-lite-latest`**.
- Never fall back to `gemini-3.5-flash-lite`, `gemini-2.5-flash-lite`, or any other Gemini model.

### Changes made
- `sitecustomize.py`
  - Removed the runtime override that configured `gemini-3.5-flash-lite` as `GEMINI_FALLBACK_MODEL`.
  - Explicitly forces `GEMINI_MODEL = "gemini-flash-lite-latest"`.
  - Sets `GEMINI_FALLBACK_MODEL = None`.
  - Updated runtime logging to state `gemini-flash-lite-latest ONLY — no fallback model`.
  - Applied the same single-model rule to `stock_query_expander`.

### Important behavior
- A Gemini quota or availability failure must **not** trigger a model switch.
- The 429 quota exhaustion seen in the 2026-08-27 GitHub Actions run is an API quota limitation, not a reason to use another model.
- Pexels/Pixabay provider fallback remains independent of Gemini model fallback.

---

## 2026-08-27 — Image-generation prohibition

### User requirement
- **Do not use Gemini or any other AI/image-generation service to generate production images.**
- Production images must be real stock assets retrieved only from Pexels or Pixabay.
- Do not introduce an AI-generated-image fallback if stock imagery is unavailable.

### Implementation rule
- Gemini is not an image-generation provider in the Mint-YT-Factory media pipeline.
- No `txt2img`, image-generation API, generative image model, or third-party AI image service may be added as a media fallback.
- The existing Pexels/Pixabay-only media-provider restriction remains authoritative for both photos and videos.
- Gemini, where still used by the project, may only perform non-generation tasks such as script/reasoning/search-direction/visual-analysis functions explicitly permitted by the project architecture.

### Decision
- A failed stock-image search must remain a stock-search failure; it must never silently become an AI-generated image.

---

## 2026-09-09 — Current implementation baseline / persistent project state

This entry is a **state snapshot**, not a new feature. It records the implementation currently present on `main` so future repository work starts from the correct architecture and does not reintroduce already-fixed problems.

### 1. Project scope
- Repository: `LetNashCode/Mint-YT-Factory`.
- Two independent production tracks exist:
  - **Publish Shorts** — curiosity/fact/explainer Shorts.
  - **Riddles Shorts** — independent interactive riddle Shorts.
- Riddles Shorts must remain isolated from Publish Shorts changes unless the user explicitly asks to modify both.

### 2. Publish Shorts — current production architecture
Primary flow is centered in `main.py` and runs roughly:
1. Refresh YouTube analytics and learning playbook.
2. Select the next topic through `topics.py` / learning signals.
3. Generate a 7-scene entertainment-first script through `generate_script.py` and its package modules.
4. Lock the current topic and canonical next topic.
5. Remove model-authored continuation from Scene 7 and append a deterministic natural bridge.
6. Generate narration with Kokoro/Edge fallback through `tts.py`.
7. Generate Pexels/Pixabay-only visuals through the resilient stock-media pipeline.
8. Generate narration-aware SFX.
9. Download music.
10. Assemble the final Short.
11. Validate video quality.
12. Upload to YouTube.
13. Publish to Instagram/Facebook when enabled.
14. Record topic/analytics/learning metadata.

Important Publish Shorts behavior:
- Current topic and next topic are treated as separate canonical states.
- Scene 7 is supposed to finish the current topic before the deterministic continuation bridge.
- The description is for the current topic only; it must not describe the next topic.
- Topic progression is committed only after successful YouTube publication/bookkeeping.
- Failed social publication must preserve the generated YouTube-ready artifact so a later run can resume social work rather than regenerate the Short.

### 3. Publish Shorts — continuation protection
Files/logic involved include `main.py`, `topics.py`, `production_entry.py`, and runtime compatibility hooks.
- `_lock_canonical_topic()` validates and locks the exact successor.
- `_strip_model_continuation_from_scene7()` removes model-authored future-topic material before the canonical bridge.
- `_generate_natural_bridge()` creates a varied spoken handoff.
- `lock_next_topic()` appends the bridge and stores the teaser metadata.
- A workflow restore bug was fixed so the Publish workflow checks only the latest failed run for a resumable artifact instead of resurrecting arbitrary old failed artifacts.
- This prevents an old failed `final.mp4` from blocking topic progression indefinitely.
- A symptom-specific Scene 7 runtime guard also exists for an earlier ice-cube continuation bleed; future continuation fixes should preserve the broader canonical-lock architecture rather than hard-code individual topics.

### 4. Publish Shorts — TTS/narration state
- `tts.py` is the primary narration engine; current implementation uses Kokoro as primary and Edge as fallback.
- `tts_bridge.py` separately protects the final continuation bridge and trims near-silence at clip edges to reduce perceived dead air/cutoff.
- The continuation bridge is intentionally short and voice-priority.
- The repository has an in-progress narration-duration requirement: the user requested **30–60 seconds**, but the current `production_entry.py` guard may still contain the older 35.0–44.95 second values and `tts.py` may still target 43.70 seconds. This is a known pending implementation item and must not be described as completed until verified on `main`.
- The previously reported ending problem was not merely missing silence: the continuation sentence could be audibly chopped before completing. The bridge protection work was implemented to address this end-to-end.

### 5. Publish Shorts — caption synchronization
Current caption architecture is:
- `whisper_align.py` obtains Whisper word timing anchors while preserving the exact script/TTS words as authoritative text.
- `assemble.py` builds one-word kinetic captions from the alignment.
- Alignment was hardened so only exact word matches become anchors; mismatches no longer become misleading anchors.
- Final caption word end-times are intentionally held through the start of the next spoken word instead of trusting Whisper's sometimes-early word-end timestamp.
- Commits implementing this were `2a4e31ec280dd7bdfb5c95f3868e96010fb8c094` and `d1d04e2e9230b7c1da4b4fb366623cc79f15c481`.
- If captions still appear mismatched, inspect the remaining `assemble.py` maximum caption duration constraint and then consider more direct forced alignment; do not replace authoritative script text with ASR text.

### 6. Publish Shorts — visual relevance and quality lessons
A recent audit of an uploaded Short showed the important failure mode to avoid:
- Some clips were relevant to the narration, but several were unrelated filler or only loosely related.
- Examples included unrelated night-sky, city-road, sponge and generic-water footage in a toes/water story.
- Repeated shots reduced visual progression.
- The visual system must therefore move toward sentence/beat-level semantic relevance, stronger rejection of unrelated stock, less repetition, and more entertaining/quirky visual progression.
- Pexels/Pixabay-only production media remains mandatory; do not solve relevance problems by adding AI image generation.

### 7. Publish Shorts — SFX
- `sfx.py` has been upgraded into a narration-aware/fun director.
- It selects semantic SFX categories from narration/context, prefers local meme assets where available, and uses short procedural stingers as fallbacks.
- Supported semantic categories include record scratch, crowd gasp, dramatic reveal, cartoon boing, Windows-style error, sad trombone, airhorn, plus pop/boing/reveal/bruh/glitch/whoosh defaults.
- Scene 7 is voice-priority and SFX is disabled there to protect the continuation bridge.
- `sfx_runtime.py` maps narration/context keywords to SFX categories.
- Known architectural consideration: `assemble.py` currently places SFX using scene time while narration can be duration-scaled, so SFX timing should be audited if beat-level synchronization problems appear.

### 8. Publish Shorts — social publishing
Meta publishing is configured for:
- Facebook Page: **Real Fun Fact**, Page ID `119624746024989`.
- Instagram Business account: `realfunfact`, account ID `17841402914072153`.
- Secrets/variables include `INSTAGRAM_ACCOUNT_ID`, `INSTAGRAM_ACCESS_TOKEN`, `FACEBOOK_PAGE_ID`, and `FACEBOOK_PAGE_ACCESS_TOKEN`.
- Repository variables include `META_GRAPH_API_VERSION=v23.0` and `SOCIAL_PUBLISH_STRICT=true`.
- The workflow maps the Instagram account ID into the publishing configuration.
- Strict social mode means social failure fails the workflow after YouTube publication; it does not roll back a successful YouTube upload.
- Social publishing has an independent retry budget of 3 total attempts per enabled destination.
- Instagram and Facebook are independent: failure on one does not prevent the other from receiving its full retry budget.
- Successful platforms are not retried.
- Social retries regenerate the Meta-compatible derivative with progressively safer encoding profiles.
- YouTube state is preserved across social failures so later runs can resume social work.
- A prior issue was that Facebook/Instagram publication did not appear on the expected destinations; future debugging should inspect the platform result/status and Meta Graph response rather than assuming upload success from the YouTube result.

### 9. Publish Shorts — upload/encoding quality
Current master validation target:
- 2160×3840
- 60 fps
- H.264
- yuv420p
- target upload bitrate 100 Mbps
- minimum accepted upload bitrate 80 Mbps

A recent generated master validated at 2160×3840, 60 fps, H.264/yuv420p, approximately 98.65 Mbps, and passed the configured quality gate.

A separate uploaded audit copy was only 512×910/30 fps at approximately 4.52 Mbps, so reduced/social copies must not be confused with the master-production quality target.

### 10. Publish Shorts — YouTube OAuth failure state
A recent Publish Shorts run successfully generated and validated a new master but YouTube upload failed with:
`google.auth.exceptions.RefreshError: invalid_grant: Token has been expired or revoked.`
This is a credential state problem, not a topic/rendering problem.
`upload_youtube.py` currently loads `YOUTUBE_TOKEN_JSON` or `token.json` and uses authorized-user credentials. A valid refreshed/re-authorized token is required before that pending video can be uploaded.

### 11. Publish Shorts — self-learning / analytics
- `learning_context.py`, `learning_engine.py`, `youtube_analytics.py`, `topic_history.py`, and related analytics files form the self-learning layer.
- Analytics are refreshed before generation where available.
- Published creative metadata is recorded for future learning, including topic category, hook type, story structure, visual style, music type, voice, and engagement experiment.
- Engagement experiments are sequential and intended to avoid generic like/subscribe language.
- Learning/analytics failures are generally non-fatal so production can continue when analytics services are unavailable.

### 12. Riddles Shorts — current architecture
Riddles are intentionally implemented as an independent pipeline.
- Workflow: `.github/workflows/riddles-shorts.yml`.
- Entry point: `interactive_main.py`.
- Topic/riddle state: `interactive_topics.py`.
- Script generator: `generate_script/interactive.py`.
- Narration polish: `riddle_narration.py`.
- Analytics: `interactive_analytics.py`.
- It uses Kokoro voice `am_michael` with a fun/warm/playful/suspenseful riddle-host tone.
- Each episode is exactly 7 scenes.
- A previous riddle's answer is deterministically revealed at the beginning of the next Short.
- The new riddle answer remains locked and must not be shown during the challenge/countdown.
- The script uses a flexible narration length and does not use the Publish Shorts word contract.
- The current riddle pool is a small fixed list of 30 classic/wordplay/logic/trick/observation riddles.
- Topic selection is currently random among unused riddles, not performance-ranked.
- Current riddle retention structure is Scene 1 previous-answer reveal/pivot, Scenes 2–3 challenge/misdirection, Scenes 4–5 thinking/reactions, Scene 6 short countdown, Scene 7 cliffhanger.
- `riddle_narration.py` adds deterministic variation across reveal/transition/ending wording and removes long 10-to-1 countdowns.
- Riddle analytics currently records videos and calculates average views/comments/shares/likes, but it does not yet use those metrics to automatically choose the next riddle or optimize hooks.
- The current Riddles pipeline is therefore functional but has a clear growth limitation: generic repeated riddle inventory + random selection + predictable structure + limited analytics feedback loop.

### 13. Riddles Shorts — planned improvement direction (NOT YET IMPLEMENTED)
The next Riddles optimization phase should focus on views/retention, without changing the Publish Shorts pipeline:
- Replace/augment generic classic riddles with original high-curiosity riddles.
- Add candidate scoring for curiosity, difficulty, surprise, visual potential, comment potential, and replay potential.
- Generate/select stronger first-1–2-second hooks.
- Vary the underlying story mechanics, not just sentences.
- Add visual-puzzle formats where the visual itself is part of the challenge.
- Build stronger open loops and more psychologically compelling endings.
- Connect `interactive_analytics.py` to selection/creative learning so future riddles favor formats that actually earn views/comments/shares.
- Preserve answer secrecy while generating visuals and countdown beats.

### 14. Known pending issues / do not mark as completed
- Publish Shorts narration guard still needs verification/implementation of the requested 30–60 second range.
- Publish Shorts `tts.py` target duration should be reconciled with the 30–60 second requirement if natural durations up to 60 seconds are desired.
- Scene 7 continuation protection should remain universal; avoid adding one-off topic-specific regexes as the primary architecture.
- Stock-media selection still needs stronger beat-level relevance/repetition rejection.
- Caption timing may need another pass if real generated videos still show mismatch after the current Whisper end-boundary fix.
- Riddle Shorts needs a dedicated retention/virality upgrade before judging the format from current low-view performance.
- YouTube OAuth token needs reauthorization if the current `invalid_grant` state remains.

### 15. Repository operating rules
For every future Mint-YT-Factory request:
1. Read this changelog before making project changes.
2. Inspect the current `main` branch before claiming a feature is implemented; historical commits alone are not proof that a change is currently active.
3. Keep Publish Shorts and Riddles Shorts isolated unless explicitly asked to change both.
4. Preserve the Pexels/Pixabay-only production media rule.
5. Preserve `gemini-flash-lite-latest` as the only Gemini model unless the user explicitly changes that requirement.
6. Do not add AI-generated production images.
7. After implementing a change, append a dated entry describing the requirement, files changed, implementation, behavior, and any remaining limitations.
8. Never silently delete or rewrite historical entries.
9. If a new request conflicts with a logged requirement, explicitly identify the conflict before changing behavior.
10. When a bug is fixed, record both the root cause and the architectural fix so future work does not regress to the old solution.

---

## Change-log operating rule

For future Mint-YT-Factory changes:
1. **Read this file before making project changes.**
2. Treat the accumulated requirements and decisions here as persistent project constraints unless the user explicitly changes them.
3. After implementing a requested change, append a dated entry describing:
   - the user's requirement,
   - files changed,
   - what was changed,
   - important behavior/constraints,
   - any relevant bugs or decisions.
4. Never silently overwrite or remove historical entries.
5. If a new request conflicts with an existing logged requirement, ask/confirm which requirement should take precedence rather than silently changing behavior.

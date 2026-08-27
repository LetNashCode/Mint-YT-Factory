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

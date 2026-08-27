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

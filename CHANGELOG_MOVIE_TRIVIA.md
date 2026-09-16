# Movie Trivia Pipeline Change Log

## 2026-09-16 — Fully automatic Movie Trivia Shorts pipeline

### User requirement
- Movie Trivia Shorts must run automatically without filling workflow inputs for every run.
- The pipeline should generate the topic and narration, find PlayPhrase clips, use Kokoro for narration, render the Short, and publish it.

### Changes made
- Replaced the manual-input flow in `.github/workflows/movie-trivia.yml` with a scheduled workflow.
- Added a daily schedule at 18:00 IST and retained `workflow_dispatch` without inputs for manual reruns.
- Added automatic Gemini episode generation using `gemini-flash-lite-latest` only.
- Added a Playwright-based PlayPhrase browser adapter that captures playable MP4 responses from the site.
- Added fail-closed behavior: if PlayPhrase does not expose a playable clip, the pipeline does not substitute stock or AI-generated media.
- Reworked `movie_trivia_main.py` to generate a hook, narration, movie-trivia metadata, PlayPhrase queries, and YouTube metadata automatically.
- Reused the repository Kokoro-based `tts.py` narration engine.
- Added visual-loop handling so the captured clip reel continues until narration ends.
- Added automatic YouTube upload through the existing `upload_youtube.py` module.
- Added a GitHub Actions artifact upload for debugging and recovery.

### Required one-time repository secrets
- `GEMINI_API_KEY`
- `YOUTUBE_TOKEN_JSON`

### Isolation and limitations
- This is a separate Movie Trivia production line and does not modify Publish Shorts or Story Shorts behavior.
- The pipeline does not use stock media or AI-generated production visuals.
- PlayPhrase is accessed through a browser because it does not provide a documented public API; site changes or anti-automation controls may cause a run to fail rather than silently use unrelated media.
- Clip rights must be independently confirmed before enabling automatic public publishing.

## 2026-09-16 — Removed redundant PlayPhrase acknowledgment secret

- Removed the custom `PLAYPHRASE_LICENSE_ACK` GitHub secret requirement from the workflow and Python entry point.
- The setting was not a PlayPhrase credential or API requirement; it was only an internal safety gate.
- The pipeline now uses the existing `GEMINI_API_KEY` and `YOUTUBE_TOKEN_JSON` secrets already used by the other production lines.
- Metadata now records a rights notice instead of falsely marking rights as programmatically acknowledged.

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

## 2026-09-17 — Resilient PlayPhrase query handling

- Added `movie_trivia_runner.py` as the workflow entry point.
- PlayPhrase browser timeouts and other per-query capture errors are now logged and skipped instead of immediately terminating the entire job.
- Remaining Gemini-generated PlayPhrase queries are still attempted.
- The pipeline remains fail-closed: if no playable clip can be captured, the run ends with a clear error and does not substitute unrelated media.
- Updated `.github/workflows/movie-trivia.yml` to use the resilient runner.

## 2026-09-17 — Improved PlayPhrase media discovery

- Added support for both the current Clip Search route and the legacy search route.
- Added browser-language headers and a Chromium automation compatibility flag.
- Added network-response discovery for MP4, WebM, and M4V media.
- Added DOM discovery for `video`, `source`, and downloadable media links.
- Removed the fragile `locator("video").first.get_attribute(..., timeout=...)` call that caused the reported timeout.
- Individual query failures remain isolated; the pipeline still stops safely if no playable clip is found.

## 2026-09-17 — Replaced FFmpeg drawtext hook rendering

- The workflow failed because the installed FFmpeg build reported `No such filter: 'drawtext'`.
- Replaced FFmpeg text rendering with Pillow-based PNG generation.
- FFmpeg now converts the generated hook-card PNG into a video, avoiding dependence on the optional `drawtext` filter.
- Added `Pillow` to the Movie Trivia workflow dependencies.
- Existing Publish Shorts and Story Shorts pipelines were not changed.

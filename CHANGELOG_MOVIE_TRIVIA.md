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

## 2026-09-17 — Replaced Movie Trivia Shorts with Reddit Horror Commentary Shorts

- Added `reddit_horror_commentary.py` as the new production entry point.
- Replaced the Movie Trivia workflow behavior while retaining the existing workflow filename for continuity.
- The scheduled workflow now discovers high-engagement video posts from selected Reddit horror communities.
- Added `yt-dlp` media downloading, Gemini commentary generation, Kokoro narration, Pillow hook-card rendering, FFmpeg assembly, and automatic YouTube publishing.
- YouTube descriptions include the original Reddit post URL and the original Reddit username.
- The new line uses the existing `GEMINI_API_KEY` and `YOUTUBE_TOKEN_JSON` secrets.
- Existing Publish Shorts, Story Shorts, Movie Trivia source files, and Movie Meme Shorts remain untouched; only the former Movie Trivia workflow is repurposed.
- The operator remains responsible for independently clearing the rights to any selected footage before publication.

## 2026-09-17 — Fixed Reddit discovery after HTTP 403 responses

- Added Reddit RSS discovery as the primary source because Reddit JSON endpoints can return HTTP 403 from GitHub Actions runners.
- Retained Reddit JSON as a best-effort fallback when RSS is unavailable.
- Removed the restrictive requirement that RSS entries expose `is_video` or `post_hint` fields.
- Changed media acquisition to pass the original Reddit post URL to `yt-dlp`, allowing yt-dlp to resolve Reddit-hosted video variants instead of relying on guessed direct media URLs.
- Added a Pillow font fallback to avoid failures when the DejaVu font path is unavailable.

## 2026-09-17 — Hardened Gemini JSON parsing

- Added defensive parsing for Gemini responses, including fenced JSON, embedded JSON objects, and literal control characters inside generated strings.
- Converts malformed Gemini output into a clear runtime error instead of exposing a raw `JSONDecodeError` traceback.

## 2026-09-17 — Added Reddit media fallback and candidate retries

- Extracts direct `v.redd.it` or media-file links exposed in RSS entries before attempting `yt-dlp`.
- Handles Reddit authentication blocks from `yt-dlp` without an immediate unhandled traceback.
- Tries up to 20 discovered candidates and skips unavailable or non-downloadable posts.
- Uses the configured `MINT_KOKORO_VOICE` and `MINT_KOKORO_LANG` environment variables for narration.

## 2026-09-17 — Added Reddit media-variant download attempts

- Extracts the Reddit media ID from `v.redd.it` links.
- Tries Reddit-hosted `DASH_720`, `DASH_480`, `DASH_360`, and `HLSPlaylist` media variants before falling back to `yt-dlp`.
- Prevents automatic redirects into the blocked `/video/` endpoint.
- Rejects HTML and JSON responses as invalid media files.
- Preserves candidate retry behavior when Reddit blocks a media source.

## 2026-09-17 — Retried Reddit CDN requests with fallback parameters

- Updated the Reddit CDN request headers to resemble a normal browser request.
- Added `?source=fallback` to Reddit DASH and HLS media URLs.
- Added explicit `Accept`, `Referer`, and `Origin` headers for media requests.
- Added cleanup for invalid or undersized downloaded files.
- Kept redirect protection and the existing candidate-retry behavior.

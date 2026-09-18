# Changelog

## 2026-09-18

- Added `yt-dlp` as a dependency for downloading approved YouTube source videos.
- Updated `mystery_footage_shorts.py` to download YouTube videos through `yt-dlp` and retain direct HTTP downloads for other approved source URLs.
- Preserved the existing rights-verification gate: automatically discovered YouTube candidates remain blocked until case facts and reuse rights are reviewed and verified.
- Added a one-word caption overlay stage for mystery-footage Shorts.
- Switched the mystery-footage demo workflow to Kokoro's male `am_michael` voice for a deeper narration style.
- Enabled demo processing of discovered footage while keeping uploads private for review.

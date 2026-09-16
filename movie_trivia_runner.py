"""Resilient PlayPhrase adapter for the automatic Movie Trivia pipeline.

PlayPhrase is a dynamic browser application. This runner uses several compatible
page routes and discovers media from network responses and rendered media elements.
Each query is isolated: a browser failure skips that query instead of aborting the job.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import movie_trivia_main as pipeline


def _capture_playphrase_clip(query: str, output_path: Path) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError("playwright is required for automatic PlayPhrase capture.") from error

    media_body: bytes | None = None
    media_url: str | None = None
    routes = (
        f"https://www.playphrase.me/#/clip-search?language=en&q={quote(query)}",
        f"https://www.playphrase.me/#/search?language=en&q={quote(query)}",
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 1000},
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        page = context.new_page()

        def inspect_response(response) -> None:
            nonlocal media_body, media_url
            if media_body is not None:
                return
            response_url = response.url.lower()
            content_type = (response.headers.get("content-type") or "").lower()
            if any(token in response_url for token in (".mp4", ".webm", ".m4v")) or "video/" in content_type:
                try:
                    body = response.body()
                    if len(body) > 20_000:
                        media_body = body
                        media_url = response.url
                except Exception:
                    return

        page.on("response", inspect_response)
        print(f"🎞️ Searching PlayPhrase: {query}")

        for route in routes:
            try:
                page.goto(route, wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(10_000)
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ PlayPhrase page load failed: {type(exc).__name__}: {exc}")
                continue

            if media_body is not None:
                break

            # Do not call get_attribute() on a missing locator: that was the original
            # failure mode. Inspect the DOM without waiting for a video element.
            try:
                candidates = page.evaluate(
                    """() => Array.from(document.querySelectorAll('video, video source, a[href], source'))
                    .map(node => node.currentSrc || node.src || node.href || '')
                    .filter(value => value && /^https?:/i.test(value))"""
                )
            except Exception:
                candidates = []

            for candidate in candidates:
                candidate_lower = candidate.lower()
                if not any(token in candidate_lower for token in (".mp4", ".webm", ".m4v", "video")):
                    continue
                try:
                    response = context.request.get(candidate, timeout=30_000)
                    body = response.body()
                    if response.ok and len(body) > 20_000:
                        media_body = body
                        media_url = candidate
                        break
                except Exception:
                    continue
            if media_body is not None:
                break

        browser.close()

    if media_body is None:
        print(f"⚠️ No playable PlayPhrase clip captured for: {query}")
        return False

    output_path.write_bytes(media_body)
    print(f"✅ Captured PlayPhrase clip: {output_path.name} ({len(media_body)} bytes) from {media_url}")
    return True


# Override the original adapter with the more defensive implementation above.
pipeline.capture_playphrase_clip = _capture_playphrase_clip


if __name__ == "__main__":
    pipeline.main()

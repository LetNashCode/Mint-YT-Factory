"""Run Story Shorts with identity-first archival media routing enabled."""
from __future__ import annotations

import runpy

import story_identity_media


def main() -> None:
    import stock_media_resilient

    original = stock_media_resilient.generate_media

    def identity_generate_media(script, output_dir, config, gim=None):
        is_story = isinstance(script, dict) and bool(str(script.get("story_person") or "").strip())
        if is_story:
            person = str(script.get("story_person") or "").strip()
            story_identity_media.begin_story(person)
            print(f"👤 Identity-first Story routing enabled for: {person}")
        try:
            return original(script, output_dir, config, gim=gim)
        finally:
            if is_story:
                story_identity_media.end_story()

    stock_media_resilient.generate_media = identity_generate_media
    runpy.run_path("interactive_main.py", run_name="__main__")


if __name__ == "__main__":
    main()

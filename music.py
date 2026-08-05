import os
import random
import requests

API_URL = "https://freesound.org/apiv2/search/text/"


def _search(api_key, query):

    params = {

        "query": query,

        "fields": "id,name,previews,tags",

        "filter": "tag:music duration:[20 TO 300]",

        "sort": "score",

        "token": api_key,

    }

    response = requests.get(
        API_URL,
        params=params,
        timeout=60,
    )

    response.raise_for_status()

    return response.json().get("results", [])


def download_music(script, workdir):

    os.makedirs(workdir, exist_ok=True)

    api_key = os.environ["FREESOUND_API_KEY"]

    searches = [

        script.get("music_search", ""),

        "science documentary",

        "educational documentary",

        "technology ambient",

        "cinematic curiosity",

        "uplifting orchestral",

        "future technology",

        "space ambient",

        "nature documentary",

        "light cinematic",

        "corporate cinematic",

        "motivational",

        "inspiring",

        "educational",

    ]

    selected = None

    for query in searches:

        if not query:
            continue

        print("=" * 80)
        print("🎵 SEARCHING MUSIC")
        print(query)
        print("=" * 80)

        try:

            results = _search(
                api_key,
                query,
            )

            if results:

                random.shuffle(results)

                selected = results[0]

                break

        except Exception as e:

            print(e)

    if selected is None:

        print("⚠️ No suitable music found.")

        return None

    preview = (

        selected.get("previews", {}).get("preview-hq-mp3")

        or

        selected.get("previews", {}).get("preview-lq-mp3")

    )

    if not preview:

        print("⚠️ Preview unavailable.")

        return None

    print("=" * 80)
    print("🎵 SELECTED MUSIC")
    print(selected["name"])
    print("=" * 80)

    output = os.path.join(
        workdir,
        "background.mp3",
    )

    audio = requests.get(
        preview,
        timeout=120,
    )

    audio.raise_for_status()

    with open(output, "wb") as f:
        f.write(audio.content)

    print(f"Saved: {output}")

    return output

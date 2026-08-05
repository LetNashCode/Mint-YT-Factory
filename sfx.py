import os
import random
import requests

API_URL = "https://freesound.org/apiv2/search/text/"


def search_sound(api_key, query):

    params = {

        "query": query,

        "fields": "id,name,previews,tags",

        "filter": "duration:[0 TO 12]",

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


def download_sfx(script, workdir):

    os.makedirs(workdir, exist_ok=True)

    api_key = os.environ["FREESOUND_API_KEY"]

    downloads = []

    fallback = [

        "whoosh",

        "soft whoosh",

        "digital beep",

        "notification",

        "camera shutter",

        "page flip",

        "click",

        "light impact",

        "ui click",

        "pop",

        "bubble",

        "sparkle",

        "swish",

    ]

    searches = script.get("sfx_search", [])

    if not searches:

        searches = fallback

    for keyword in searches:

        print("=" * 80)
        print("💥 SEARCHING SFX")
        print(keyword)
        print("=" * 80)

        try:

            results = search_sound(
                api_key,
                keyword,
            )

            if not results:

                continue

            random.shuffle(results)

            sound = results[0]

            preview = (

                sound.get("previews", {}).get("preview-hq-mp3")

                or

                sound.get("previews", {}).get("preview-lq-mp3")

            )

            if not preview:

                continue

            filename = os.path.join(

                workdir,

                keyword.replace(
                    " ",
                    "_",
                )
                + ".mp3",

            )

            audio = requests.get(
                preview,
                timeout=120,
            )

            audio.raise_for_status()

            with open(filename, "wb") as f:

                f.write(audio.content)

            print("Downloaded:", keyword)

            downloads.append(filename)

        except Exception as e:

            print(e)

    return downloads

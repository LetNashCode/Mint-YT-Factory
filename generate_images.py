def generate_image(prompt, width, height):

    url = "https://image.pollinations.ai/prompt/cat"

    print(url)

    response = requests.get(
        url,
        timeout=180,
    )

    response.raise_for_status()

    return response.content

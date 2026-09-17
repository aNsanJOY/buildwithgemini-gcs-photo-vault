"""Public photo search tool for GCS Photo Vault using Openverse API."""

import os
import httpx


def search_public_photos(query: str, limit: int = 3) -> str:
    """Searches free public domain and Creative Commons photos for inspiration or visual reference.

    Args:
        query: Search keyword (e.g. 'Kyoto cherry blossoms', 'sunset beach', 'Yosemite mountain').
        limit: Number of photo results to return (default: 3, max: 5).

    Returns:
        A list of matching public photos with title, creator, license, and direct image URL.
    """
    api_key = os.environ.get("OPENVERSE_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    limit = min(max(1, limit), 5)
    url = f"https://api.openverse.org/v1/images/?q={query}&page_size={limit}"

    try:
        response = httpx.get(url, headers=headers, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])

        if not results:
            return f"No public domain photos found for query: '{query}'."

        photos = []
        for i, photo in enumerate(results, 1):
            title = photo.get("title", "Untitled Photo")
            image_url = photo.get("url")
            creator = photo.get("creator", "Unknown Creator")
            license_code = photo.get("license", "CC").upper()
            photos.append(
                f"{i}. Title: {title}\n"
                f"   Creator: {creator} (License: {license_code})\n"
                f"   Image URL: {image_url}"
            )

        return f"Found {len(results)} public photos for '{query}':\n\n" + "\n\n".join(photos)
    except Exception as e:
        return f"Error fetching public photos: {type(e).__name__}: {e}"

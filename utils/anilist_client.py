import random
from typing import Optional

import aiohttp

ANILIST_ENDPOINT = "https://graphql.anilist.co"

MEDIA_FIELDS = """
    id
    type
    format
    status
    episodes
    chapters
    volumes
    averageScore
    popularity
    genres
    countryOfOrigin
    siteUrl
    isAdult
    description(asHtml: false)
    title {
        romaji
        english
        native
    }
    coverImage {
        large
        color
    }
    startDate {
        year
    }
"""

SEARCH_QUERY = f"""
query ($search: String, $type: MediaType, $perPage: Int, $isAdult: Boolean) {{
    Page(page: 1, perPage: $perPage) {{
        media(search: $search, type: $type, isAdult: $isAdult, sort: SEARCH_MATCH) {{
            {MEDIA_FIELDS}
        }}
    }}
}}
"""

DISCOVER_QUERY = f"""
query ($type: MediaType, $genre: String, $page: Int, $perPage: Int, $sort: [MediaSort], $isAdult: Boolean) {{
    Page(page: $page, perPage: $perPage) {{
        pageInfo {{
            total
        }}
        media(type: $type, genre: $genre, isAdult: $isAdult, sort: $sort) {{
            {MEDIA_FIELDS}
        }}
    }}
}}
"""

RECOMMENDATIONS_QUERY = f"""
query ($id: Int) {{
    Media(id: $id) {{
        recommendations(sort: RATING_DESC, perPage: 10) {{
            nodes {{
                mediaRecommendation {{
                    {MEDIA_FIELDS}
                }}
            }}
        }}
    }}
}}
"""

BY_ID_QUERY = f"""
query ($id: Int) {{
    Media(id: $id) {{
        {MEDIA_FIELDS}
    }}
}}
"""

GENRES = [
    "Action", "Adventure", "Comedy", "Drama", "Ecchi", "Fantasy", "Horror",
    "Mahou Shoujo", "Mecha", "Music", "Mystery", "Psychological", "Romance",
    "Sci-Fi", "Slice of Life", "Sports", "Supernatural", "Thriller",
]


async def _post(session: aiohttp.ClientSession, query: str, variables: dict) -> Optional[dict]:
    clean_variables = {k: v for k, v in variables.items() if v is not None}
    try:
        async with session.post(
            ANILIST_ENDPOINT,
            json={"query": query, "variables": clean_variables},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as resp:
            if resp.status != 200:
                return None
            payload = await resp.json()
            if "errors" in payload:
                return None
            return payload.get("data")
    except (aiohttp.ClientError, TimeoutError):
        return None


async def search_media(session: aiohttp.ClientSession, query_text: str, media_type: str = "ANIME", limit: int = 5, is_adult: Optional[bool] = False) -> list[dict]:
    data = await _post(session, SEARCH_QUERY, {"search": query_text, "type": media_type, "perPage": limit, "isAdult": is_adult})
    if not data:
        return []
    return data.get("Page", {}).get("media", [])


async def get_media_by_id(session: aiohttp.ClientSession, media_id: int) -> Optional[dict]:
    data = await _post(session, BY_ID_QUERY, {"id": media_id})
    if not data:
        return None
    return data.get("Media")


async def get_recommendations_for(session: aiohttp.ClientSession, media_id: int) -> list[dict]:
    data = await _post(session, RECOMMENDATIONS_QUERY, {"id": media_id})
    if not data:
        return []
    nodes = data.get("Media", {}).get("recommendations", {}).get("nodes", [])
    return [n["mediaRecommendation"] for n in nodes if n.get("mediaRecommendation")]


async def discover_random(session: aiohttp.ClientSession, media_type: str = "ANIME", genre: Optional[str] = None, sort: str = "POPULARITY_DESC", is_adult: Optional[bool] = False) -> Optional[dict]:
    first_page = await _post(session, DISCOVER_QUERY, {
        "type": media_type, "genre": genre, "page": 1, "perPage": 1, "sort": [sort], "isAdult": is_adult,
    })
    if not first_page:
        return None

    total = first_page.get("Page", {}).get("pageInfo", {}).get("total", 0)
    if total <= 0:
        return None

    max_page = min(total, 300)
    target_page = random.randint(1, max(1, max_page))

    target_data = await _post(session, DISCOVER_QUERY, {
        "type": media_type, "genre": genre, "page": target_page, "perPage": 1, "sort": [sort], "isAdult": is_adult,
    })
    if not target_data:
        return None

    media_list = target_data.get("Page", {}).get("media", [])
    return media_list[0] if media_list else None


async def get_trending(session: aiohttp.ClientSession, media_type: str = "ANIME", limit: int = 10) -> list[dict]:
    data = await _post(session, DISCOVER_QUERY, {
        "type": media_type, "genre": None, "page": 1, "perPage": limit, "sort": ["TRENDING_DESC"],
    })
    if not data:
        return []
    return data.get("Page", {}).get("media", [])


def display_title(media: dict) -> str:
    titles = media.get("title", {})
    return titles.get("english") or titles.get("romaji") or titles.get("native") or "Unknown Title"


def clean_description(media: dict, limit: int = 400) -> str:
    description = media.get("description") or "No description available."
    description = description.replace("<br>", "\n").replace("<i>", "").replace("</i>", "")
    description = description.replace("<b>", "").replace("</b>", "")
    if len(description) > limit:
        description = description[:limit - 3] + "..."
    return description

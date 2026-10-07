import time
from typing import Optional

import aiohttp

import config

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_API_BASE = "https://api.twitch.tv/helix"

_twitch_token: Optional[str] = None
_twitch_token_expires_at: float = 0.0


class YouTubeClient:

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def resolve_channel_id(self, handle_or_id: str) -> Optional[dict]:
        handle_or_id = handle_or_id.strip()
        if handle_or_id.startswith("UC") and len(handle_or_id) == 24:
            params = {"part": "snippet,contentDetails", "id": handle_or_id, "key": config.YOUTUBE_API_KEY}
        elif handle_or_id.startswith("@"):
            params = {"part": "snippet,contentDetails", "forHandle": handle_or_id, "key": config.YOUTUBE_API_KEY}
        else:
            params = {"part": "snippet,contentDetails", "forUsername": handle_or_id, "key": config.YOUTUBE_API_KEY}

        async with self.session.get(f"{YOUTUBE_API_BASE}/channels", params=params) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        items = data.get("items", [])
        if not items:
            return None

        channel = items[0]
        uploads_playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]
        return {
            "channel_id": channel["id"],
            "title": channel["snippet"]["title"],
            "thumbnail": channel["snippet"]["thumbnails"].get("default", {}).get("url", ""),
            "uploads_playlist_id": uploads_playlist_id,
        }

    async def get_latest_upload(self, uploads_playlist_id: str) -> Optional[dict]:
        params = {
            "part": "snippet,contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": 1,
            "key": config.YOUTUBE_API_KEY,
        }
        async with self.session.get(f"{YOUTUBE_API_BASE}/playlistItems", params=params) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        items = data.get("items", [])
        if not items:
            return None

        item = items[0]
        video_id = item["contentDetails"]["videoId"]
        return {
            "video_id": video_id,
            "title": item["snippet"]["title"],
            "thumbnail": item["snippet"]["thumbnails"].get("high", item["snippet"]["thumbnails"].get("default", {})).get("url", ""),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "published_at": item["snippet"]["publishedAt"],
        }

    async def is_live(self, video_id: str) -> bool:
        params = {"part": "snippet", "id": video_id, "key": config.YOUTUBE_API_KEY}
        async with self.session.get(f"{YOUTUBE_API_BASE}/videos", params=params) as resp:
            if resp.status != 200:
                return False
            data = await resp.json()

        items = data.get("items", [])
        if not items:
            return False
        return items[0]["snippet"].get("liveBroadcastContent") == "live"


class TwitchClient:

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def _get_token(self) -> Optional[str]:
        global _twitch_token, _twitch_token_expires_at

        if _twitch_token and time.time() < _twitch_token_expires_at - 60:
            return _twitch_token

        if not config.TWITCH_CLIENT_ID or not config.TWITCH_CLIENT_SECRET:
            return None

        params = {
            "client_id": config.TWITCH_CLIENT_ID,
            "client_secret": config.TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials",
        }
        async with self.session.post(TWITCH_AUTH_URL, params=params) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        _twitch_token = data["access_token"]
        _twitch_token_expires_at = time.time() + data.get("expires_in", 3600)
        return _twitch_token

    async def _headers(self) -> Optional[dict]:
        token = await self._get_token()
        if not token:
            return None
        return {"Client-Id": config.TWITCH_CLIENT_ID, "Authorization": f"Bearer {token}"}

    async def resolve_user(self, login: str) -> Optional[dict]:
        headers = await self._headers()
        if not headers:
            return None

        async with self.session.get(f"{TWITCH_API_BASE}/users", params={"login": login.lower()}, headers=headers) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        items = data.get("data", [])
        if not items:
            return None
        user = items[0]
        return {"user_id": user["id"], "login": user["login"], "display_name": user["display_name"], "avatar": user["profile_image_url"]}

    async def get_streams(self, user_logins: list[str]) -> dict[str, dict]:
        headers = await self._headers()
        if not headers or not user_logins:
            return {}

        results = {}
        for batch_start in range(0, len(user_logins), 100):
            batch = user_logins[batch_start:batch_start + 100]
            params = [("user_login", login.lower()) for login in batch]
            async with self.session.get(f"{TWITCH_API_BASE}/streams", params=params, headers=headers) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()

            for stream in data.get("data", []):
                results[stream["user_login"].lower()] = {
                    "stream_id": stream["id"],
                    "title": stream["title"],
                    "game_name": stream.get("game_name", ""),
                    "thumbnail": stream["thumbnail_url"].replace("{width}", "1280").replace("{height}", "720"),
                    "started_at": stream["started_at"],
                    "viewer_count": stream["viewer_count"],
                }
        return results

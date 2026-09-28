from __future__ import annotations

from collections.abc import Iterator

from ..http import HttpClient
from ..models import VideoAsset
from .base import VideoSource, choose_variant, duration_allowed


class PixabaySource(VideoSource):
    name = "pixabay"
    endpoint = "https://pixabay.com/api/videos/"

    def __init__(self, client: HttpClient, api_key: str) -> None:
        self.client = client
        self.api_key = api_key

    def search(
        self,
        query: str,
        *,
        limit: int,
        min_width: int,
        max_width: int,
        min_duration: float | None,
        max_duration: float | None,
    ) -> Iterator[VideoAsset]:
        data = self.client.get_json(
            self.endpoint,
            params={
                "key": self.api_key,
                "q": query,
                "per_page": min(200, max(3, limit * 2)),
                "min_width": min_width,
                "safesearch": "true",
            },
            cache_ttl=24 * 60 * 60,
        )
        yielded = 0
        for item in data.get("hits", []):
            duration = float(item["duration"]) if item.get("duration") is not None else None
            if not duration_allowed(duration, min_duration, max_duration):
                continue
            variants = [
                {
                    "url": value.get("url"),
                    "width": value.get("width"),
                    "height": value.get("height"),
                    "mime": "video/mp4",
                }
                for value in (item.get("videos") or {}).values()
                if isinstance(value, dict)
            ]
            selected = choose_variant(variants, min_width=min_width, max_width=max_width)
            if not selected:
                continue
            author = str(item.get("user") or "Pixabay contributor")
            page_url = str(item.get("pageURL") or "")
            yield VideoAsset(
                source=self.name,
                source_id=str(item.get("id")),
                title=f"Pixabay video {item.get('id')}",
                page_url=page_url,
                download_url=str(selected["url"]),
                width=int(selected.get("width") or 0),
                height=int(selected.get("height") or 0),
                duration=duration,
                mime_type="video/mp4",
                author=author,
                author_url=(
                    f"https://pixabay.com/users/{author}-{item.get('user_id')}/"
                    if item.get("user_id")
                    else ""
                ),
                license_name="Pixabay Content License",
                license_url="https://pixabay.com/service/license-summary/",
                attribution=f"Video by {author} on Pixabay ({page_url})",
                restrictions="No standalone distribution; review trademarks, people and other third-party rights.",
            )
            yielded += 1
            if yielded >= limit:
                return

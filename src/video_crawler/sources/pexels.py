from __future__ import annotations

from collections.abc import Iterator

from ..http import HttpClient
from ..models import VideoAsset
from .base import VideoSource, choose_variant, duration_allowed


class PexelsSource(VideoSource):
    name = "pexels"
    supports_browse = True
    endpoint = "https://api.pexels.com/v1/videos/search"
    popular_endpoint = "https://api.pexels.com/v1/videos/popular"

    def __init__(self, client: HttpClient, api_key: str) -> None:
        self.client = client
        self.api_key = api_key

    def _query_params(
        self,
        *,
        limit: int,
        min_width: int,
        max_width: int,
        min_duration: float | None,
        max_duration: float | None,
        query: str | None = None,
    ) -> dict:
        params: dict = {
            "per_page": min(80, max(1, limit * 2)),
            **({"min_width": min_width} if min_width else {}),
            **({"min_duration": int(min_duration)} if min_duration is not None else {}),
            **({"max_duration": int(max_duration)} if max_duration is not None else {}),
        }
        if query is not None:
            params["query"] = query
        return params

    def _iter_videos(
        self,
        endpoint: str,
        params: dict,
        *,
        limit: int,
        min_width: int,
        max_width: int,
        min_duration: float | None,
        max_duration: float | None,
    ) -> Iterator[VideoAsset]:
        data = self.client.get_json(
            endpoint,
            params=params,
            headers={"Authorization": self.api_key},
        )
        yielded = 0
        for item in data.get("videos", []):
            duration = float(item["duration"]) if item.get("duration") is not None else None
            if not duration_allowed(duration, min_duration, max_duration):
                continue
            variants = [
                {
                    "url": file.get("link"),
                    "width": file.get("width"),
                    "height": file.get("height"),
                    "mime": file.get("file_type"),
                }
                for file in item.get("video_files", [])
                if file.get("file_type") in {"video/mp4", "video/webm"}
            ]
            selected = choose_variant(variants, min_width=min_width, max_width=max_width)
            if not selected:
                continue
            user = item.get("user") or {}
            author = str(user.get("name") or "Pexels contributor")
            page_url = str(item.get("url") or "")
            yield VideoAsset(
                source=self.name,
                source_id=str(item.get("id")),
                title=f"Pexels video {item.get('id')}",
                page_url=page_url,
                download_url=str(selected["url"]),
                width=int(selected.get("width") or 0),
                height=int(selected.get("height") or 0),
                duration=duration,
                mime_type=str(selected.get("mime") or "video/mp4"),
                author=author,
                author_url=str(user.get("url") or ""),
                license_name="Pexels License",
                license_url="https://www.pexels.com/license/",
                attribution=f"Video by {author} on Pexels ({page_url})",
                restrictions="No standalone resale/redistribution; review people, brands and endorsement use.",
            )
            yielded += 1
            if yielded >= limit:
                return

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
        yield from self._iter_videos(
            self.endpoint,
            self._query_params(
                limit=limit,
                min_width=min_width,
                max_width=max_width,
                min_duration=min_duration,
                max_duration=max_duration,
                query=query,
            ),
            limit=limit,
            min_width=min_width,
            max_width=max_width,
            min_duration=min_duration,
            max_duration=max_duration,
        )

    def browse(
        self,
        *,
        limit: int,
        min_width: int,
        max_width: int,
        min_duration: float | None,
        max_duration: float | None,
    ) -> Iterator[VideoAsset]:
        yield from self._iter_videos(
            self.popular_endpoint,
            self._query_params(
                limit=limit,
                min_width=min_width,
                max_width=max_width,
                min_duration=min_duration,
                max_duration=max_duration,
            ),
            limit=limit,
            min_width=min_width,
            max_width=max_width,
            min_duration=min_duration,
            max_duration=max_duration,
        )


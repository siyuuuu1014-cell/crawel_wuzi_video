from __future__ import annotations

from collections.abc import Iterator

from ..http import HttpClient
from ..models import VideoAsset
from .base import VideoSource, duration_allowed


class CoverrSource(VideoSource):
    name = "coverr"
    supports_browse = True
    endpoint = "https://api.coverr.co/videos"

    def __init__(self, client: HttpClient, api_key: str) -> None:
        self.client = client
        self.api_key = api_key

    def _iter_videos(
        self,
        params: dict,
        *,
        limit: int,
        min_width: int,
        max_width: int,
        min_duration: float | None,
        max_duration: float | None,
    ) -> Iterator[VideoAsset]:
        data = self.client.get_json(
            self.endpoint,
            params=params,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        yielded = 0
        for item in data.get("hits") or []:
            width = int(item.get("max_width") or 0)
            height = int(item.get("max_height") or 0)
            if width < min_width:
                continue
            duration = float(item["duration"]) if item.get("duration") is not None else None
            if not duration_allowed(duration, min_duration, max_duration):
                continue
            urls = item.get("urls") or {}
            download_url = str(urls.get("mp4_download") or urls.get("mp4") or "")
            source_id = str(item.get("id") or "")
            if not source_id or not download_url:
                continue
            title = str(item.get("title") or f"Coverr video {source_id}")
            page_url = f"https://coverr.co/videos/{source_id}"
            yield VideoAsset(
                source=self.name,
                source_id=source_id,
                title=title,
                page_url=page_url,
                download_url=download_url,
                width=width,
                height=height,
                duration=duration,
                mime_type="video/mp4",
                author="Coverr contributor",
                author_url="https://coverr.co/",
                license_name="Coverr License",
                license_url="https://coverr.co/license",
                attribution=f"{title} — Coverr ({page_url})",
                restrictions=(
                    "Use through the approved Coverr API key and follow its API/license terms; "
                    "do not resell or redistribute the unmodified file as a competing library."
                ),
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
            {
                "query": query,
                "page_size": min(100, max(1, limit * 2)),
                "sort": "date",
                "urls": "true",
            },
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
            {
                "page_size": min(100, max(1, limit * 2)),
                "sort": "date",
                "urls": "true",
            },
            limit=limit,
            min_width=min_width,
            max_width=max_width,
            min_duration=min_duration,
            max_duration=max_duration,
        )

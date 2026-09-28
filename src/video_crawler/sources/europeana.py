from __future__ import annotations

import urllib.parse
from collections.abc import Iterator
from typing import Any

from ..http import HttpClient
from ..models import VideoAsset
from .base import VideoSource, duration_allowed
from .licenses import identify_open_license, infer_video_mime, text_values


class EuropeanaSource(VideoSource):
    name = "europeana"
    supports_browse = True
    endpoint = "https://api.europeana.eu/record/v2/search.json"

    def __init__(self, client: HttpClient, api_key: str) -> None:
        self.client = client
        self.api_key = api_key

    def _iter_items(
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
                "wskey": self.api_key,
                "query": query,
                "reusability": "open",
                "media": "true",
                "profile": "rich",
                "rows": min(100, max(1, limit * 3)),
                "sort": "random asc",
            },
            cache_ttl=60 * 60,
        )
        yielded = 0
        for item in data.get("items") or []:
            asset = self._map_item(item)
            if asset is None:
                continue
            yield asset
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
        # Search API dimensions/duration are not consistently returned per item.
        if min_width > 0 or min_duration is not None or max_duration is not None:
            return
        yield from self._iter_items(
            f"({query}) AND TYPE:VIDEO",
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
        # Search API dimensions/duration are not consistently returned per item.
        if min_width > 0 or min_duration is not None or max_duration is not None:
            return
        yield from self._iter_items(
            "TYPE:VIDEO",
            limit=limit,
            min_width=min_width,
            max_width=max_width,
            min_duration=min_duration,
            max_duration=max_duration,
        )

    def _map_item(self, item: dict[str, Any]) -> VideoAsset | None:
        if str(item.get("type") or "").upper() != "VIDEO":
            return None
        rights = item.get("rights") or item.get("edmRights")
        license_info = identify_open_license(name=rights, url=rights)
        if license_info is None:
            return None
        media_urls = text_values(item.get("edmIsShownBy")) + text_values(item.get("edmHasView"))
        download_url = next((_direct_video_url(url) for url in media_urls if _direct_video_url(url)), "")
        if not download_url:
            return None
        source_id = str(item.get("id") or "").strip("/")
        if not source_id:
            return None
        titles = text_values(item.get("title")) or text_values(item.get("dcTitle"))
        title = titles[0] if titles else source_id
        creators = text_values(item.get("dcCreator"))
        author = creators[0] if creators else "Europeana data provider"
        pages = text_values(item.get("guid")) + text_values(item.get("edmIsShownAt"))
        page_url = pages[0] if pages else f"https://www.europeana.eu/item/{source_id}"
        license_name, license_url = license_info
        return VideoAsset(
            source=self.name,
            source_id=source_id,
            title=title,
            page_url=page_url,
            download_url=download_url,
            width=0,
            height=0,
            duration=None,
            mime_type=infer_video_mime(download_url),
            author=author,
            author_url=page_url,
            license_name=license_name,
            license_url=license_url,
            attribution=f"{title} — {author} — {license_name} ({page_url})",
            restrictions=(
                "Europeana aggregates provider-hosted media. Open-reuse and direct-video "
                "filters were applied; verify the provider page and item-specific rights."
            ),
        )


def _direct_video_url(url: str) -> str:
    path = urllib.parse.urlsplit(url).path.casefold()
    return url.replace("http://", "https://", 1) if path.endswith(
        (".mp4", ".webm", ".ogv", ".ogg", ".mov")
    ) else ""

from __future__ import annotations

import urllib.parse
from collections.abc import Iterator

from ..http import HttpClient, HttpError, RateLimitError
from ..models import VideoAsset
from .base import VideoSource


class NasaSource(VideoSource):
    name = "nasa"
    supports_browse = True
    endpoint = "https://images-api.nasa.gov/search"
    fallback_queries = (
        "earth",
        "space",
        "moon",
        "mars",
        "rocket",
        "astronaut",
        "satellite",
        "sun",
        "galaxy",
        "science",
    )

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def _iter_items(
        self,
        query: str | None,
        *,
        limit: int,
        min_width: int,
        max_width: int,
        min_duration: float | None,
        max_duration: float | None,
    ) -> Iterator[VideoAsset]:
        yielded = 0
        seen_ids: set[str] = set()
        search_queries = [query] if query is not None else [None]
        for search_query in search_queries:
            page = 1
            while yielded < limit and page <= 5:
                params: dict[str, object] = {
                    "media_type": "video",
                    "page_size": min(100, max(10, limit - yielded)),
                    "page": page,
                }
                if search_query is not None:
                    params["q"] = search_query
                data = self.client.get_json(self.endpoint, params=params)
                items = data.get("collection", {}).get("items", [])
                if not items:
                    break
                for item in items:
                    asset = self._map_item(item)
                    if not asset or asset.source_id in seen_ids:
                        continue
                    seen_ids.add(asset.source_id)
                    yield asset
                    yielded += 1
                    if yielded >= limit:
                        return
                page += 1
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
        # The search result does not expose reliable dimensions/duration.
        if min_width > 0 or min_duration is not None or max_duration is not None:
            return
        search_queries = [query] + [
            value for value in self.fallback_queries if value.casefold() != query.casefold()
        ]
        yielded = 0
        seen_ids: set[str] = set()
        for search_query in search_queries:
            page = 1
            while yielded < limit and page <= 5:
                data = self.client.get_json(
                    self.endpoint,
                    params={
                        "q": search_query,
                        "media_type": "video",
                        "page_size": min(100, max(10, limit - yielded)),
                        "page": page,
                    },
                )
                items = data.get("collection", {}).get("items", [])
                if not items:
                    break
                for item in items:
                    asset = self._map_item(item)
                    if not asset or asset.source_id in seen_ids:
                        continue
                    seen_ids.add(asset.source_id)
                    yield asset
                    yielded += 1
                    if yielded >= limit:
                        return
                page += 1
        return

    def browse(
        self,
        *,
        limit: int,
        min_width: int,
        max_width: int,
        min_duration: float | None,
        max_duration: float | None,
    ) -> Iterator[VideoAsset]:
        # The search result does not expose reliable dimensions/duration.
        if min_width > 0 or min_duration is not None or max_duration is not None:
            return
        yield from self._iter_items(
            None,
            limit=limit,
            min_width=min_width,
            max_width=max_width,
            min_duration=min_duration,
            max_duration=max_duration,
        )

    def _map_item(self, item: dict) -> VideoAsset | None:
        metadata_items = item.get("data") or []
        if not metadata_items:
            return None
        metadata = metadata_items[0]
        # NASA marks third-party protected media with a copyright owner.
        if str(metadata.get("copyright") or "").strip():
            return None
        nasa_id = str(metadata.get("nasa_id") or "").strip()
        manifest_url = str(item.get("href") or "")
        if not nasa_id or not manifest_url:
            return None
        try:
            files = [str(value) for value in self.client.get_json_list(manifest_url)]
        except RateLimitError:
            raise
        except HttpError:
            return None
        download_url = _choose_mp4(files)
        if not download_url:
            return None
        author = str(
            metadata.get("secondary_creator")
            or metadata.get("center")
            or "NASA"
        )
        title = str(metadata.get("title") or nasa_id)
        page_url = f"https://images.nasa.gov/details/{urllib.parse.quote(nasa_id)}"
        return VideoAsset(
            source=self.name,
            source_id=nasa_id,
            title=title,
            page_url=page_url,
            download_url=download_url,
            width=0,
            height=0,
            duration=None,
            mime_type="video/mp4",
            author=author,
            author_url="https://www.nasa.gov/",
            license_name="NASA Media Usage Guidelines",
            license_url="https://www.nasa.gov/nasa-brand-center/images-and-media/",
            attribution=f"{title} — {author}/NASA ({page_url})",
            restrictions=(
                "NASA content is generally not copyrighted in the U.S.; do not imply "
                "endorsement. Review logos, identifiable people and jurisdiction-specific rights."
            ),
        )


def _choose_mp4(files: list[str]) -> str:
    mp4s = [url.replace("http://", "https://", 1) for url in files if url.lower().endswith(".mp4")]
    for marker in ("~medium.mp4", "~large.mp4", "~small.mp4", "~mobile.mp4", "~preview.mp4", "~orig.mp4"):
        match = next((url for url in mp4s if url.lower().endswith(marker)), None)
        if match:
            return match
    return mp4s[0] if mp4s else ""

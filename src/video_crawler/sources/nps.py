from __future__ import annotations

from collections.abc import Iterator

from ..http import HttpClient
from ..models import VideoAsset
from .base import VideoSource, choose_variant, duration_allowed


class NpsSource(VideoSource):
    name = "nps"
    supports_browse = True
    endpoint = "https://developer.nps.gov/api/v1/multimedia/videos"

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
            headers={"X-Api-Key": self.api_key},
        )
        yielded = 0
        for item in data.get("data") or []:
            asset = self._map_item(item, min_width=min_width, max_width=max_width)
            if not asset or not duration_allowed(asset.duration, min_duration, max_duration):
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
        yield from self._iter_videos(
            {"q": query, "limit": min(50, max(10, limit * 2)), "start": 0},
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
        page_size = min(50, max(10, limit * 2))
        start = 0
        yielded = 0
        while yielded < limit:
            produced = 0
            for asset in self._iter_videos(
                {"limit": page_size, "start": start},
                limit=limit - yielded,
                min_width=min_width,
                max_width=max_width,
                min_duration=min_duration,
                max_duration=max_duration,
            ):
                produced += 1
                yield asset
                yielded += 1
                if yielded >= limit:
                    return
            if produced == 0:
                return
            start += page_size

    def _map_item(self, item: dict, *, min_width: int, max_width: int) -> VideoAsset | None:
        combined = " ".join(
            str(item.get(field) or "") for field in ("title", "description", "copyright")
        ).casefold()
        if any(marker in combined for marker in (
            "all rights reserved", "copyrighted", "courtesy of", "used with permission",
        )):
            return None
        variants = [
            {
                "url": version.get("url"),
                "width": version.get("widthPixels") or 0,
                "height": version.get("heightPixels") or 0,
                "mime_type": version.get("fileType") or "video/mp4",
            }
            for version in item.get("versions") or []
            if str(version.get("fileType") or "").casefold().startswith("video/")
        ]
        selected = choose_variant(variants, min_width=min_width, max_width=max_width)
        source_id = str(item.get("id") or "").strip()
        if not source_id or not selected:
            return None
        title = str(item.get("title") or f"NPS video {source_id}")
        page_url = str(item.get("permalinkUrl") or f"https://www.nps.gov/media/video/view.htm?id={source_id}")
        credit = str(item.get("credit") or "National Park Service").strip()
        duration_ms = item.get("durationMs")
        duration = float(duration_ms) / 1000 if duration_ms is not None else None
        return VideoAsset(
            source=self.name,
            source_id=source_id,
            title=title,
            page_url=page_url,
            download_url=str(selected["url"]).replace("http://", "https://", 1),
            width=int(selected.get("width") or 0),
            height=int(selected.get("height") or 0),
            duration=duration,
            mime_type=str(selected.get("mime_type") or "video/mp4"),
            author=credit,
            author_url="https://www.nps.gov/",
            license_name="NPS Public Domain / Website Disclaimer",
            license_url="https://www.nps.gov/aboutus/disclaimer.htm",
            attribution=f"{title} — {credit}/NPS ({page_url})",
            restrictions=(
                "NPS-created U.S. government material is generally public domain unless noted. "
                "Check the source page for third-party material, trademarks, donor, privacy and "
                "publicity restrictions; do not imply NPS endorsement."
            ),
        )


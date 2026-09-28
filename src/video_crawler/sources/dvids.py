from __future__ import annotations

from collections.abc import Iterator

from ..http import HttpClient, HttpError, RateLimitError
from ..models import VideoAsset
from .base import VideoSource, choose_variant, duration_allowed


class DvidsSource(VideoSource):
    name = "dvids"
    search_endpoint = "https://api.dvidshub.net/search"
    asset_endpoint = "https://api.dvidshub.net/asset"

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
            self.search_endpoint,
            params={
                "api_key": self.api_key,
                "q": query,
                "type": "video",
                "max_results": min(50, max(10, limit * 2)),
                "page": 1,
                "hd": 1,
            },
        )
        yielded = 0
        for result in data.get("results") or []:
            asset_id = str(result.get("id") or "").strip()
            if not asset_id:
                continue
            try:
                detail_data = self.client.get_json(
                    self.asset_endpoint,
                    params={"api_key": self.api_key, "id": asset_id},
                )
            except RateLimitError:
                raise
            except HttpError:
                continue
            detail = detail_data.get("results") or {}
            asset = self._map_item(detail, min_width=min_width, max_width=max_width)
            if not asset or not duration_allowed(asset.duration, min_duration, max_duration):
                continue
            yield asset
            yielded += 1
            if yielded >= limit:
                return

    def _map_item(self, item: dict, *, min_width: int, max_width: int) -> VideoAsset | None:
        combined = " ".join(
            str(item.get(field) or "") for field in ("title", "description", "copyright")
        ).casefold()
        if any(marker in combined for marker in (
            "all rights reserved", "copyrighted", "courtesy of", "licensed by",
        )):
            return None
        variants = []
        for file in item.get("files") or []:
            if not str(file.get("type") or "").casefold().startswith("video/"):
                continue
            variants.append({
                "url": file.get("src"),
                "width": file.get("width") or 0,
                "height": file.get("height") or 0,
                "mime_type": file.get("type") or "video/mp4",
                "size": file.get("size") or 0,
            })
        selected = choose_variant(variants, min_width=min_width, max_width=max_width)
        source_id = str(item.get("id") or "").removeprefix("video:").strip()
        if not source_id or not selected:
            return None
        title = str(item.get("title") or f"DVIDS video {source_id}")
        page_url = str(item.get("url") or f"https://www.dvidshub.net/video/{source_id}")
        credits = item.get("credit") or []
        if isinstance(credits, list):
            names = [
                " ".join(filter(None, (str(value.get("rank") or "").strip(), str(value.get("name") or "").strip())))
                for value in credits if isinstance(value, dict)
            ]
            author = ", ".join(filter(None, names)) or "DVIDS"
            author_url = next(
                (str(value.get("url")) for value in credits if isinstance(value, dict) and value.get("url")),
                "https://www.dvidshub.net/",
            )
        else:
            author = str(credits or "DVIDS")
            author_url = "https://www.dvidshub.net/"
        duration = float(item["duration"]) if item.get("duration") is not None else None
        return VideoAsset(
            source=self.name,
            source_id=source_id,
            title=title,
            page_url=page_url,
            download_url=str(selected["url"]),
            width=int(selected.get("width") or 0),
            height=int(selected.get("height") or 0),
            duration=duration,
            mime_type=str(selected.get("mime_type") or "video/mp4"),
            author=author,
            author_url=author_url,
            license_name="DVIDS Public Use Notice",
            license_url="https://www.dvidshub.net/about/copyright",
            attribution=f"{title} — {author}/DVIDS ({page_url})",
            restrictions=(
                "U.S. government works on DVIDS are generally public domain, but third-party "
                "material, privacy/publicity rights and military marks may still be restricted. "
                "Do not imply Department of Defense endorsement; review the source page."
            ),
        )


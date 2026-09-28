from __future__ import annotations

import urllib.parse
from collections.abc import Iterator
from typing import Any

from ..http import HttpClient, HttpError, RateLimitError
from ..models import VideoAsset
from .base import VideoSource, duration_allowed
from .licenses import identify_open_license, infer_video_mime, text_values


class InternetArchiveSource(VideoSource):
    name = "archive"
    supports_browse = True
    search_endpoint = "https://archive.org/advancedsearch.php"
    metadata_endpoint = "https://archive.org/metadata"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

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
        yielded = 0
        page = 1
        while yielded < limit and page <= 5:
            data = self.client.get_json(
                self.search_endpoint,
                params={
                    "q": query,
                    "fl[]": "identifier",
                    "rows": min(100, max(20, (limit - yielded) * 4)),
                    "page": page,
                    "output": "json",
                },
            )
            docs = (data.get("response") or {}).get("docs") or []
            if not docs:
                return
            for doc in docs:
                identifier = str(doc.get("identifier") or "").strip()
                if not identifier:
                    continue
                try:
                    metadata = self.client.get_json(
                        f"{self.metadata_endpoint}/{urllib.parse.quote(identifier, safe='')}",
                        cache_ttl=24 * 60 * 60,
                    )
                except RateLimitError:
                    raise
                except HttpError:
                    continue
                asset = self._map_item(
                    identifier,
                    metadata,
                    min_width=min_width,
                    max_width=max_width,
                    min_duration=min_duration,
                    max_duration=max_duration,
                )
                if asset is None:
                    continue
                yield asset
                yielded += 1
                if yielded >= limit:
                    return
            page += 1

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
        yield from self._iter_items(
            f"mediatype:movies AND licenseurl:* AND ({query})",
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
        yield from self._iter_items(
            "mediatype:movies AND licenseurl:*",
            limit=limit,
            min_width=min_width,
            max_width=max_width,
            min_duration=min_duration,
            max_duration=max_duration,
        )

    def _map_item(
        self,
        identifier: str,
        data: dict[str, Any],
        *,
        min_width: int,
        max_width: int,
        min_duration: float | None,
        max_duration: float | None,
    ) -> VideoAsset | None:
        metadata = data.get("metadata") or {}
        # Internet Archive accepts user uploads, so a recognized license URL is mandatory.
        license_info = identify_open_license(url=metadata.get("licenseurl"))
        if license_info is None:
            return None
        selected = _choose_archive_mp4(
            data.get("files") or [], min_width=min_width, max_width=max_width
        )
        if selected is None:
            return None
        duration = _duration(selected.get("length") or metadata.get("runtime"))
        if not duration_allowed(duration, min_duration, max_duration):
            return None
        filename = str(selected["name"])
        download_url = (
            f"https://archive.org/download/{urllib.parse.quote(identifier, safe='')}/"
            f"{urllib.parse.quote(filename, safe='/')}"
        )
        page_url = f"https://archive.org/details/{urllib.parse.quote(identifier, safe='')}"
        titles = text_values(metadata.get("title"))
        title = titles[0] if titles else identifier
        creators = text_values(metadata.get("creator"))
        author = creators[0] if creators else "Internet Archive contributor"
        license_name, license_url = license_info
        return VideoAsset(
            source=self.name,
            source_id=identifier,
            title=title,
            page_url=page_url,
            download_url=download_url,
            width=int(selected.get("width") or 0),
            height=int(selected.get("height") or 0),
            duration=duration,
            mime_type=infer_video_mime(download_url),
            author=author,
            author_url=page_url,
            license_name=license_name,
            license_url=license_url,
            attribution=f"{title} — {author} — {license_name} ({page_url})",
            restrictions=(
                "Internet Archive metadata is uploader-supplied. The crawler requires an open "
                "license URL, but the item page and third-party rights still require review."
            ),
        )


def _choose_archive_mp4(
    files: list[dict[str, Any]], *, min_width: int, max_width: int
) -> dict[str, Any] | None:
    candidates = []
    for item in files:
        name = str(item.get("name") or "")
        lowered = name.casefold()
        if not lowered.endswith(".mp4") or any(
            marker in lowered for marker in ("_sample", "thumb", "trailer")
        ):
            continue
        width = _int(item.get("width"))
        if width < min_width:
            continue
        size = _int(item.get("size"))
        fmt = str(item.get("format") or "").casefold()
        priority = 0 if "512kb" in fmt or "512kb" in lowered else 1 if "h.264" in fmt else 2
        within_max = width == 0 or width <= max_width
        candidates.append((not within_max, priority, size or 2**63, item))
    return min(candidates, key=lambda value: value[:3])[3] if candidates else None


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _duration(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        parts = str(value).split(":")
        try:
            total = 0.0
            for part in parts:
                total = total * 60 + float(part)
            return total
        except ValueError:
            return None

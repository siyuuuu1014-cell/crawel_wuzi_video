from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ..http import HttpClient
from ..models import VideoAsset
from .base import VideoSource, choose_variant, duration_allowed
from .licenses import identify_open_license, infer_video_mime, text_values


class LibraryOfCongressSource(VideoSource):
    name = "loc"
    supports_browse = True
    endpoint = "https://www.loc.gov/film-and-videos/"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def _iter_results(
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
        page = 1
        while yielded < limit and page <= 5:
            params: dict[str, Any] = {
                "fo": "json",
                "at": "results",
                "c": min(100, max(20, (limit - yielded) * 3)),
                "sp": page,
            }
            if query is not None:
                params["q"] = query
            data = self.client.get_json(self.endpoint, params=params)
            items = data.get("results") or []
            if not items:
                return
            for item in items:
                asset = self._map_item(
                    item,
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
        yield from self._iter_results(
            query,
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
        yield from self._iter_results(
            None,
            limit=limit,
            min_width=min_width,
            max_width=max_width,
            min_duration=min_duration,
            max_duration=max_duration,
        )

    def _map_item(
        self,
        item: dict[str, Any],
        *,
        min_width: int,
        max_width: int,
        min_duration: float | None,
        max_duration: float | None,
    ) -> VideoAsset | None:
        if item.get("access_restricted"):
            return None
        rights = text_values(item.get("rights")) + text_values(item.get("rights_advisory"))
        license_info = identify_open_license(
            name=rights,
            url=rights,
            allow_public_domain_text=True,
        )
        if license_info is None:
            return None
        variants = _loc_video_variants(item.get("resources") or [])
        selected = choose_variant(variants, min_width=min_width, max_width=max_width)
        if selected is None:
            return None
        duration = _float_or_none(selected.get("duration"))
        if not duration_allowed(duration, min_duration, max_duration):
            return None
        page_url = str(item.get("url") or item.get("id") or "").replace("http://", "https://", 1)
        if not page_url:
            return None
        source_id = page_url.rstrip("/").rsplit("/", 1)[-1]
        authors = text_values(item.get("contributor")) or text_values(item.get("creator"))
        author = authors[0] if authors else "Library of Congress"
        license_name, license_url = license_info
        download_url = str(selected["url"]).replace("http://", "https://", 1)
        title_values = text_values(item.get("title"))
        title = title_values[0] if title_values else source_id
        return VideoAsset(
            source=self.name,
            source_id=source_id,
            title=title,
            page_url=page_url,
            download_url=download_url,
            width=int(selected.get("width") or 0),
            height=int(selected.get("height") or 0),
            duration=duration,
            mime_type=str(selected.get("mime") or infer_video_mime(download_url)),
            author=author,
            author_url=page_url,
            license_name=license_name,
            license_url=license_url,
            attribution=f"{title} — {author}, Library of Congress ({page_url})",
            restrictions=(
                "Catalogue rights statement was filtered for public-domain/open reuse. "
                "Review the item page for privacy, publicity, trademark and donor restrictions."
            ),
        )


def _loc_video_variants(resources: Any) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    def visit(value: Any, restricted: bool = False) -> None:
        if isinstance(value, list):
            for nested in value:
                visit(nested, restricted)
            return
        if not isinstance(value, dict):
            return
        is_restricted = restricted or bool(
            value.get("download_restricted") or value.get("rights_restricted")
        )
        mime = str(value.get("mimetype") or value.get("mime_type") or "")
        url = str(
            value.get("download") or value.get("filename") or value.get("url") or ""
        )
        if not url:
            for key in ("video", "video_stream"):
                candidate = value.get(key)
                if isinstance(candidate, str):
                    url = candidate
                    break
        if url and not is_restricted and (
            mime.casefold().startswith("video/")
            or url.casefold().split("?", 1)[0].endswith((".mp4", ".webm", ".ogv", ".mov"))
        ):
            variants.append(
                {
                    "url": url,
                    "width": int(value.get("width") or 0),
                    "height": int(value.get("height") or 0),
                    "duration": value.get("duration"),
                    "mime": mime or infer_video_mime(url),
                }
            )
        for key in ("files", "derivatives", "streams"):
            if key in value:
                visit(value[key], is_restricted)

    visit(resources)
    return variants


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None

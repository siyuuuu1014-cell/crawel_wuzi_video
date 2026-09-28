from __future__ import annotations

import html
import re
from collections.abc import Iterator

from ..http import HttpClient
from ..models import VideoAsset
from .base import VideoSource


_TAG_RE = re.compile(r"<[^>]+>")
_DISALLOWED_LICENSE_MARKERS = ("noncommercial", "no derivatives", "cc by-nc", "cc by-nd")


def _plain(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("value", "")
    return html.unescape(_TAG_RE.sub("", str(value or ""))).strip()


def _license_allowed(name: str) -> bool:
    normalized = re.sub(r"\s+", " ", name.casefold()).strip()
    if any(marker in normalized for marker in _DISALLOWED_LICENSE_MARKERS):
        return False
    if normalized in {"cc0", "public domain", "public-domain"}:
        return True
    return bool(
        re.fullmatch(r"cc by(?:-sa)?(?: \d+(?:\.\d+)?)?", normalized)
        or re.fullmatch(
            r"creative commons attribution(?:-share ?alike)?(?: \d+(?:\.\d+)?)?",
            normalized,
        )
    )


class WikimediaCommonsSource(VideoSource):
    name = "commons"
    endpoint = "https://commons.wikimedia.org/w/api.php"

    def __init__(
        self, client: HttpClient, *, max_transcode_height: int = 720, allow_original: bool = False
    ) -> None:
        self.client = client
        self.max_transcode_height = max_transcode_height
        self.allow_original = allow_original

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
        # Commons currently does not expose reliable duration in this response.
        if min_duration is not None or max_duration is not None:
            return
        continuation: dict[str, object] = {}
        yielded = 0
        while yielded < limit:
            data = self.client.get_json(
                self.endpoint,
                params={
                    "action": "query",
                    "format": "json",
                    "formatversion": "2",
                    "generator": "search",
                    "gsrsearch": f"{query} filetype:video",
                    "gsrnamespace": 6,
                    "gsrlimit": min(50, max(10, limit - yielded)),
                    "prop": "videoinfo",
                    "viprop": "url|size|mime|dimensions|derivatives|extmetadata",
                    "viextmetadatafilter": (
                        "LicenseShortName|LicenseUrl|Artist|Credit|Attribution|"
                        "UsageTerms|Restrictions"
                    ),
                    **continuation,
                },
            )
            pages = data.get("query", {}).get("pages", [])
            if not isinstance(pages, list):
                break
            for page in pages:
                info_list = page.get("videoinfo") or []
                if not info_list:
                    continue
                info = info_list[0]
                selected = self._select_video(info, min_width=min_width, max_width=max_width)
                if not selected:
                    continue
                meta = info.get("extmetadata") or {}
                license_name = _plain(meta.get("LicenseShortName"))
                if not _license_allowed(license_name):
                    continue
                author = _plain(meta.get("Artist")) or "Wikimedia Commons contributor"
                license_url = _plain(meta.get("LicenseUrl"))
                title = str(page.get("title") or "Untitled").removeprefix("File:")
                page_url = str(info.get("descriptionurl") or "")
                attribution = _plain(meta.get("Attribution")) or _plain(meta.get("Credit"))
                if not attribution:
                    attribution = f"{title} — {author} — {license_name}"
                yield VideoAsset(
                    source=self.name,
                    source_id=str(page.get("pageid") or title),
                    title=title,
                    page_url=page_url,
                    download_url=str(selected.get("src") or selected.get("url") or ""),
                    width=int(selected.get("width") or 0),
                    height=int(selected.get("height") or 0),
                    duration=None,
                    mime_type=str(selected.get("type") or info.get("mime") or "video/webm").split(";", 1)[0],
                    author=author,
                    author_url=page_url,
                    license_name=license_name,
                    license_url=license_url,
                    attribution=attribution,
                    restrictions=_plain(meta.get("Restrictions")),
                )
                yielded += 1
                if yielded >= limit:
                    return
            next_values = data.get("continue")
            if not isinstance(next_values, dict):
                break
            continuation = next_values

    def _select_video(self, info: dict, *, min_width: int, max_width: int) -> dict | None:
        transcodes = [
            item
            for item in info.get("derivatives", [])
            if item.get("transcodekey")
            and item.get("src")
            and min_width <= int(item.get("width") or 0) <= max_width
            and int(item.get("height") or 0) <= self.max_transcode_height
        ]
        if transcodes:
            return max(
                transcodes,
                key=lambda item: (int(item.get("height") or 0), int(item.get("width") or 0)),
            )
        if self.allow_original:
            width = int(info.get("width") or 0)
            if min_width <= width <= max_width and info.get("url"):
                return {
                    "url": info["url"],
                    "width": width,
                    "height": int(info.get("height") or 0),
                    "type": info.get("mime"),
                }
        return None

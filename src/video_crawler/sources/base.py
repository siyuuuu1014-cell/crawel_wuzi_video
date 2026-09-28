from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from ..models import VideoAsset


class VideoSource(ABC):
    name: str
    supports_browse: bool = False

    @abstractmethod
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
        raise NotImplementedError

    def browse(
        self,
        *,
        limit: int,
        min_width: int,
        max_width: int,
        min_duration: float | None,
        max_duration: float | None,
    ) -> Iterator[VideoAsset]:
        raise NotImplementedError(f"{self.name} 不支持无关键词浏览")


def duration_allowed(
    duration: float | None, min_duration: float | None, max_duration: float | None
) -> bool:
    if duration is None:
        return min_duration is None and max_duration is None
    return (min_duration is None or duration >= min_duration) and (
        max_duration is None or duration <= max_duration
    )


def choose_variant(
    variants: list[dict], *, min_width: int, max_width: int
) -> dict | None:
    usable = [
        item
        for item in variants
        if item.get("url") and int(item.get("width") or 0) >= min_width
    ]
    if not usable:
        return None
    within_limit = [item for item in usable if int(item.get("width") or 0) <= max_width]
    choices = within_limit or usable
    return max(choices, key=lambda item: (int(item.get("width") or 0), int(item.get("height") or 0)))


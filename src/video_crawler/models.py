from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class VideoAsset:
    source: str
    source_id: str
    title: str
    page_url: str
    download_url: str
    width: int
    height: int
    duration: float | None
    mime_type: str
    author: str
    author_url: str
    license_name: str
    license_url: str
    attribution: str
    restrictions: str = ""

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


from __future__ import annotations

import re
import urllib.parse
from collections.abc import Iterable
from typing import Any


_CC_URL = re.compile(
    r"^https?://creativecommons\.org/(?:licenses/(by|by-sa)/([0-9.]+)|"
    r"publicdomain/(zero|mark)/([0-9.]+))(?:/|$)",
    re.IGNORECASE,
)


def text_values(value: Any) -> list[str]:
    """Flatten the simple string/list/language-map shapes used by media APIs."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        result: list[str] = []
        for nested in value.values():
            result.extend(text_values(nested))
        return result
    if isinstance(value, Iterable):
        result = []
        for nested in value:
            result.extend(text_values(nested))
        return result
    return [str(value)]


def identify_open_license(
    *, name: Any = None, url: Any = None, allow_public_domain_text: bool = False
) -> tuple[str, str] | None:
    """Return a normalized license only for licenses that permit commercial reuse.

    URL matching is deliberately strict. Text-only public-domain matching is reserved
    for institutional catalogues such as the Library of Congress.
    """
    candidates = text_values(url) + text_values(name)
    for candidate in candidates:
        match = _CC_URL.match(candidate.strip())
        if not match:
            continue
        license_code, license_version, public_code, public_version = match.groups()
        if public_code:
            label = "CC0" if public_code.casefold() == "zero" else "Public Domain Mark"
            version = public_version or "1.0"
            path = "zero" if label == "CC0" else "mark"
            return (
                f"{label} {version}",
                f"https://creativecommons.org/publicdomain/{path}/{version}/",
            )
        code = (license_code or "").upper()
        version = license_version or "4.0"
        return (
            f"CC {code} {version}",
            f"https://creativecommons.org/licenses/{code.lower()}/{version}/",
        )

    joined = " ".join(text_values(name)).casefold()
    if "cc0" in joined:
        return "CC0", "https://creativecommons.org/publicdomain/zero/1.0/"
    if re.search(r"\bcc by-sa(?:\s+[0-9.]+)?\b", joined):
        version = _license_version(joined)
        return f"CC BY-SA {version}", f"https://creativecommons.org/licenses/by-sa/{version}/"
    if re.search(r"\bcc by(?:\s+[0-9.]+)?\b", joined):
        version = _license_version(joined)
        return f"CC BY {version}", f"https://creativecommons.org/licenses/by/{version}/"
    if allow_public_domain_text and (
        "public domain" in joined or "no known restrictions" in joined
    ):
        return "Public Domain / No known restrictions", ""
    return None


def infer_video_mime(url: str, fallback: str = "video/mp4") -> str:
    path = urllib.parse.urlsplit(url).path.casefold()
    if path.endswith(".webm"):
        return "video/webm"
    if path.endswith((".ogv", ".ogg")):
        return "video/ogg"
    if path.endswith(".mov"):
        return "video/quicktime"
    return fallback


def _license_version(text: str) -> str:
    match = re.search(r"\b([1-4](?:\.0)?)\b", text)
    return match.group(1) if match else "4.0"

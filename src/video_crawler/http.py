from __future__ import annotations

import json
import hashlib
import time
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


DEFAULT_USER_AGENT = "FreeVideoCrawlerBot/0.2 (contact-not-configured)"
_SENSITIVE_QUERY_KEYS = {"key", "api_key", "apikey", "access_token", "token", "wskey"}


class HttpError(RuntimeError):
    pass


class RateLimitError(HttpError):
    def __init__(self, url: str, retry_after: int, detail: str) -> None:
        self.retry_after = retry_after
        super().__init__(
            f"服务端限流：{url}；建议至少等待 {retry_after} 秒后重试（{detail}）"
        )


def _redact_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    safe_query = [
        (key, "***" if key.casefold() in _SENSITIVE_QUERY_KEYS else value)
        for key, value in query
    ]
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(safe_query), parts.fragment)
    )


class HttpClient:
    def __init__(
        self,
        timeout: float = 30,
        retries: int = 3,
        cache_dir: Path | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.cache_dir = cache_dir
        self.user_agent = user_agent or DEFAULT_USER_AGENT

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cache_ttl: float = 0,
    ) -> dict[str, Any]:
        if params:
            encoded = urllib.parse.urlencode(params)
            url = f"{url}{'&' if '?' in url else '?'}{encoded}"
        request_headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        request_headers.update(headers or {})
        cache_path = None
        if cache_ttl > 0 and self.cache_dir:
            cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
            cache_path = self.cache_dir / f"{cache_key}.json"
            if cache_path.exists() and time.time() - cache_path.stat().st_mtime < cache_ttl:
                try:
                    cached = json.loads(cache_path.read_text(encoding="utf-8"))
                    if isinstance(cached, dict):
                        return cached
                except (OSError, json.JSONDecodeError):
                    pass
        data = self._request(urllib.request.Request(url, headers=request_headers))
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HttpError(f"接口返回了无效 JSON：{_redact_url(url)}") from exc
        if not isinstance(value, dict):
            raise HttpError(f"接口返回格式不正确：{_redact_url(url)}")
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return value

    def get_json_list(
        self, url: str, *, headers: dict[str, str] | None = None
    ) -> list[Any]:
        # Some public media manifests contain literal spaces in their path.
        url = urllib.parse.quote(url, safe=":/?&=%#[]@!$'()*+,;")
        request_headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        request_headers.update(headers or {})
        data = self._request(urllib.request.Request(url, headers=request_headers))
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HttpError(f"接口返回了无效 JSON：{_redact_url(url)}") from exc
        if not isinstance(value, list):
            raise HttpError(f"接口返回格式不正确：{_redact_url(url)}")
        return value

    def content_length(self, url: str) -> int | None:
        url = urllib.parse.quote(url, safe=":/?&=%#[]@!$'()*+,;")
        request = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": self.user_agent},
        )
        try:
            with self._open(request) as response:
                value = response.headers.get("Content-Length")
                return int(value) if value and value.isdigit() else None
        except HttpError:
            return None

    def download(
        self,
        url: str,
        destination: Path,
        *,
        progress: Callable[[int], None] | None = None,
        max_bytes: int | None = None,
    ) -> tuple[int, str]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        # Public media manifests sometimes return literal spaces or Unicode in URLs.
        url = urllib.parse.quote(url, safe=":/?&=%#[]@!$'()*+,;")
        if max_bytes is not None:
            length = self.content_length(url)
            if length is not None and length > max_bytes:
                raise HttpError(f"文件超过大小限制（{max_bytes} bytes，实际 {length}）")
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        digest = hashlib.sha256()
        size = 0
        try:
            with self._open(request) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    if max_bytes is not None and size + len(chunk) > max_bytes:
                        raise HttpError(f"文件超过大小限制（{max_bytes} bytes）")
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                    if progress:
                        progress(size)
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return size, digest.hexdigest()

    def _request(self, request: urllib.request.Request) -> bytes:
        with self._open(request) as response:
            return response.read()

    def _open(self, request: urllib.request.Request):
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                return urllib.request.urlopen(request, timeout=self.timeout)
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code == 429:
                    raise RateLimitError(
                        _redact_url(request.full_url),
                        _retry_after_seconds(exc.headers.get("Retry-After")),
                        str(exc),
                    ) from exc
                if exc.code not in {429, 500, 502, 503, 504}:
                    break
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                time.sleep(min(delay, 30))
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                time.sleep(2**attempt)
        raise HttpError(f"网络请求失败：{_redact_url(request.full_url)}（{last_error}）") from last_error


def _retry_after_seconds(value: str | None) -> int:
    if value and value.isdigit():
        return max(60, int(value))
    if value:
        try:
            target = parsedate_to_datetime(value)
            return max(60, int((target - datetime.now(timezone.utc)).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            pass
    return 15 * 60

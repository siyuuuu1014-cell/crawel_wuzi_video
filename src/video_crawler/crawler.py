from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .http import HttpClient, RateLimitError
from .models import VideoAsset
from .sources.base import VideoSource


_UNSAFE_FILENAME = re.compile(r"[^\w.-]+", re.UNICODE)


@dataclass(slots=True)
class CrawlOptions:
    output: Path
    video_dir: Path | None = None
    limit: int = 10
    min_width: int = 0
    max_width: int = 1920
    min_duration: float | None = None
    max_duration: float | None = None
    interval: float = 1.0
    commons_interval: float = 10.0
    metadata_only: bool = False
    max_file_mb: int = 500


@dataclass(slots=True)
class CrawlSummary:
    found: int = 0
    downloaded: int = 0
    completed: int = 0
    skipped: int = 0
    failed: int = 0
    rate_limited_sources: set[str] = field(default_factory=set)


def _extension(asset: VideoAsset) -> str:
    mapping = {"video/mp4": ".mp4", "video/webm": ".webm", "video/ogg": ".ogv"}
    if asset.mime_type in mapping:
        return mapping[asset.mime_type]
    suffix = Path(asset.download_url.split("?", 1)[0]).suffix.lower()
    return suffix if suffix in {".mp4", ".webm", ".ogv", ".mov"} else ".video"


def _filename(asset: VideoAsset) -> str:
    stem = _UNSAFE_FILENAME.sub("-", asset.title).strip("-._")[:80] or "video"
    source_id = _UNSAFE_FILENAME.sub("-", asset.source_id).strip("-._")
    return f"{asset.source}_{source_id}_{stem}{_extension(asset)}"


def _read_completed(manifest: Path) -> set[str]:
    completed: set[str] = set()
    if not manifest.exists():
        return completed
    with manifest.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("status") in {"downloaded", "metadata_only"} and row.get("key"):
                completed.add(str(row["key"]))
    return completed


def _append_jsonl(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def _write_credits(manifest: Path, destination: Path) -> None:
    rows: dict[str, dict] = {}
    if manifest.exists():
        with manifest.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("status") in {"downloaded", "metadata_only"}:
                    rows[str(row.get("key"))] = row
    lines = ["# 视频素材来源与署名", ""]
    for row in rows.values():
        asset = row.get("asset", {})
        title = asset.get("title", "Untitled")
        page = asset.get("page_url", "")
        license_name = asset.get("license_name", "Unknown license")
        license_url = asset.get("license_url", "")
        author = asset.get("author", "Unknown")
        lines.extend(
            [
                f"- **{title}** — {author}",
                f"  - 来源：{page}",
                f"  - 许可证：[{license_name}]({license_url})" if license_url else f"  - 许可证：{license_name}",
                f"  - 建议署名：{asset.get('attribution', '')}",
                f"  - 附加限制：{asset.get('restrictions', '') or '未在接口元数据中列出；仍需人工检查肖像、商标和场景权利。'}",
                "",
            ]
        )
    destination.write_text("\n".join(lines), encoding="utf-8")


def crawl(
    query: str,
    sources: list[VideoSource],
    client: HttpClient,
    options: CrawlOptions,
    *,
    browse: bool = False,
) -> CrawlSummary:
    options.output.mkdir(parents=True, exist_ok=True)
    videos_dir = options.video_dir or options.output / "videos"
    manifest = options.output / "manifest.jsonl"
    errors = options.output / "errors.jsonl"
    completed = _read_completed(manifest)
    summary = CrawlSummary()

    for source in sources:
        if browse:
            if not source.supports_browse:
                print(f"\n[{source.name}] 不支持无关键词浏览，跳过。", file=sys.stderr)
                continue
            print(f"\n[{source.name}] 浏览全部视频")
        else:
            print(f"\n[{source.name}] 搜索：{query}")
        accepted = 0
        try:
            if browse:
                assets = source.browse(
                    limit=min(200, max(options.limit, options.limit * 4)),
                    min_width=options.min_width,
                    max_width=options.max_width,
                    min_duration=options.min_duration,
                    max_duration=options.max_duration,
                )
            else:
                assets = source.search(
                    query,
                    # Fetch a deeper buffer so IDs completed by earlier random
                    # queries do not consume the entire quota. No request exceeds 200 rows.
                    limit=min(200, max(options.limit, options.limit * 4)),
                    min_width=options.min_width,
                    max_width=options.max_width,
                    min_duration=options.min_duration,
                    max_duration=options.max_duration,
                )
            for asset in assets:
                summary.found += 1
                if asset.key in completed:
                    summary.skipped += 1
                    print(f"  跳过（已完成）{asset.title}")
                    continue
                record = {
                    "key": asset.key,
                    "query": query,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "asset": asset.to_dict(),
                }
                if options.metadata_only:
                    record["status"] = "metadata_only"
                    _append_jsonl(manifest, record)
                    completed.add(asset.key)
                    accepted += 1
                    summary.completed += 1
                    print(f"  记录元数据：{asset.title}")
                    if accepted >= options.limit:
                        break
                    continue
                target = videos_dir / _filename(asset)
                print(f"  下载：{asset.title} ({asset.width}x{asset.height})")
                max_bytes = options.max_file_mb * 1024 * 1024

                def _show_progress(size: int, _target: int = max_bytes) -> None:
                    print(f"    {size / 1024 / 1024:.1f} / {_target / 1024 / 1024:.0f} MB", end="\r", flush=True)

                try:
                    size, sha256 = client.download(
                        asset.download_url,
                        target,
                        max_bytes=max_bytes,
                        progress=_show_progress,
                    )
                    print(" " * 40, end="\r", flush=True)
                    record.update(
                        status="downloaded",
                        local_path=_display_path(target, options.output),
                        bytes=size,
                        sha256=sha256,
                    )
                    _append_jsonl(manifest, record)
                    completed.add(asset.key)
                    accepted += 1
                    summary.downloaded += 1
                    summary.completed += 1
                    print(f"  完成：{target.name} ({size / 1024 / 1024:.1f} MB)")
                except RateLimitError as exc:
                    summary.failed += 1
                    summary.rate_limited_sources.add(source.name)
                    record.update(
                        status="rate_limited",
                        error=str(exc),
                        retry_after_seconds=exc.retry_after,
                    )
                    _append_jsonl(errors, record)
                    print(
                        f"  来源已暂停：{exc}。将继续其他网站。",
                        file=sys.stderr,
                    )
                    break
                except Exception as exc:
                    summary.failed += 1
                    record.update(status="failed", error=str(exc))
                    _append_jsonl(errors, record)
                    print(f"  失败：{exc}", file=sys.stderr)
                interval = (
                    max(options.interval, options.commons_interval)
                    if source.name == "commons"
                    else options.interval
                )
                if interval > 0:
                    time.sleep(interval)
                if accepted >= options.limit:
                    break
        except RateLimitError as exc:
            summary.failed += 1
            summary.rate_limited_sources.add(source.name)
            _append_jsonl(
                errors,
                {
                    "source": source.name,
                    "query": query,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "status": "rate_limited",
                    "retry_after_seconds": exc.retry_after,
                    "error": str(exc),
                },
            )
            print(f"  来源已暂停：{exc}。将继续其他网站。", file=sys.stderr)
        except Exception as exc:
            summary.failed += 1
            _append_jsonl(
                errors,
                {
                    "source": source.name,
                    "query": query,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "status": "search_failed",
                    "error": str(exc),
                },
            )
            print(f"  搜索失败：{exc}", file=sys.stderr)

    _write_credits(manifest, options.output / "CREDITS.md")
    return summary


def _display_path(path: Path, metadata_root: Path) -> str:
    try:
        return str(path.relative_to(metadata_root))
    except ValueError:
        return str(path.resolve())

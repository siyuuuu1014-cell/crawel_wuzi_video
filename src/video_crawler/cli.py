from __future__ import annotations

import argparse
import json
import os
import random
import sys
from dataclasses import replace
from pathlib import Path

from .crawler import CrawlOptions, CrawlSummary, crawl
from .http import HttpClient
from .source_keywords import SOURCE_KEYWORDS
from .sources import (
    CoverrSource,
    DvidsSource,
    EuropeanaSource,
    InternetArchiveSource,
    LibraryOfCongressSource,
    NasaSource,
    NpsSource,
    PexelsSource,
    PixabaySource,
    WikimediaCommonsSource,
)


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="free-video-crawler",
        description="通过官方 API 下载可再利用视频，并保存许可证和署名元数据。",
    )
    parser.add_argument("query", nargs="?", help="搜索关键词；省略时自动进入随机模式")
    parser.add_argument(
        "--browse",
        action="store_true",
        help="无关键词浏览模式：在支持的来源上遍历全部视频，不受关键词限制",
    )
    parser.add_argument(
        "--random",
        action="store_true",
        help="从关键词池随机抽取多个题材，并分散抓取配额",
    )
    parser.add_argument(
        "--keyword-file",
        type=Path,
        default=Path("random_keywords.txt"),
        help="随机模式关键词文件（默认 random_keywords.txt，每行一个）",
    )
    parser.add_argument(
        "--random-keywords",
        type=int,
        default=8,
        help="每次随机抽取的关键词数量（默认 8）",
    )
    parser.add_argument("--seed", type=int, help="随机种子，便于复现某次选择")
    parser.add_argument(
        "--source",
        default="all",
        help=(
            "来源：commons、nasa、nps、dvids、loc、archive、pexels、pixabay、"
            "coverr、europeana 或 all；可用逗号组合（默认 all）"
        ),
    )
    parser.add_argument("--limit", type=int, default=100, help="本次跨所有来源的总目标数量（默认 100）")
    parser.add_argument("--output", type=Path, default=Path("downloads"), help="输出目录")
    parser.add_argument(
        "--video-dir",
        type=Path,
        default=Path(r"D:\collected_video"),
        help=r"视频文件目录（默认 D:\collected_video）",
    )
    parser.add_argument("--min-width", type=int, default=0, help="最小宽度")
    parser.add_argument("--max-width", type=int, default=1920, help="期望的最大宽度")
    parser.add_argument("--min-duration", type=float, help="最短时长（秒）")
    parser.add_argument("--max-duration", type=float, help="最长时长（秒）")
    parser.add_argument("--interval", type=float, default=1.0, help="下载间隔秒数（默认 1）")
    parser.add_argument(
        "--commons-interval",
        type=float,
        default=10.0,
        help="Commons 下载间隔秒数下限（默认 10）",
    )
    parser.add_argument("--max-file-mb", type=int, default=500, help="单文件大小上限 MB")
    parser.add_argument(
        "--commons-max-height",
        type=int,
        default=720,
        help="Commons 官方转码最大高度（默认 720）",
    )
    parser.add_argument(
        "--commons-original",
        action="store_true",
        help="允许 Commons 原始大文件（容易触发限流，不推荐）",
    )
    parser.add_argument("--metadata-only", action="store_true", help="只生成清单，不下载视频")
    return parser


def _validate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.random and args.query:
        parser.error("关键词与 --random 不能同时使用")
    if args.random_keywords < 1:
        parser.error("--random-keywords 必须大于 0")
    if not 1 <= args.limit <= 200:
        parser.error("--limit 必须在 1 到 200 之间")
    if args.min_width < 0 or args.max_width < 1 or args.min_width > args.max_width:
        parser.error("分辨率范围无效")
    if args.interval < 0 or args.commons_interval < 0 or args.max_file_mb < 1:
        parser.error("--interval 不能为负，--max-file-mb 必须大于 0")
    if (
        args.min_duration is not None
        and args.max_duration is not None
        and args.min_duration > args.max_duration
    ):
        parser.error("时长范围无效")
    if args.commons_max_height < 144:
        parser.error("--commons-max-height 不能小于 144")


def _load_keyword_pool(path: Path) -> list[str]:
    if not path.exists():
        raise ValueError(f"关键词文件不存在：{path}")
    keywords = []
    seen = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        keyword = raw_line.strip()
        if not keyword or keyword.startswith("#") or keyword.casefold() in seen:
            continue
        seen.add(keyword.casefold())
        keywords.append(keyword)
    if not keywords:
        raise ValueError(f"关键词文件中没有可用关键词：{path}")
    return keywords


def _choose_random_queries(
    pool: list[str],
    *,
    count: int,
    limit: int,
    seed: int | str | None,
    recent: list[str] | tuple[str, ...] = (),
) -> list[str]:
    actual_count = min(count, limit, len(pool))
    recent_keys = {value.casefold() for value in recent}
    fresh = [value for value in pool if value.casefold() not in recent_keys]
    candidates = fresh if len(fresh) >= actual_count else pool
    return random.Random(seed).sample(candidates, actual_count)


def _load_keyword_history(path: Path) -> list[str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    keywords = value.get("keywords") if isinstance(value, dict) else None
    return [str(item) for item in keywords] if isinstance(keywords, list) else []


def _save_keyword_history(path: Path, previous: list[str], selected: list[str]) -> None:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in reversed(previous + selected):
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"keywords": list(reversed(ordered[:64]))}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _build_source_queries(
    sources: list,
    general_queries: list[str],
    *,
    count: int,
    limit: int,
    seed: int | None,
    recent: list[str],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for source in sources:
        pool = list(SOURCE_KEYWORDS.get(source.name, ()))
        if not pool:
            result[source.name] = general_queries
            continue
        source_seed: str | None = f"{seed}:{source.name}" if seed is not None else None
        result[source.name] = _choose_random_queries(
            pool,
            count=count,
            limit=limit,
            seed=source_seed,
            recent=recent,
        )
    return result


def _allocate(total: int, groups: int) -> list[int]:
    base, remainder = divmod(total, groups)
    return [base + (1 if index < remainder else 0) for index in range(groups)]


def _merge_summary(target: CrawlSummary, source: CrawlSummary) -> None:
    target.found += source.found
    target.downloaded += source.downloaded
    target.completed += source.completed
    target.skipped += source.skipped
    target.failed += source.failed
    target.rate_limited_sources.update(source.rate_limited_sources)


def main(argv: list[str] | None = None) -> None:
    _load_dotenv()
    parser = _parser()
    args = parser.parse_args(argv)
    if args.browse:
        if args.random or args.query:
            parser.error("--browse 与关键词或 --random 不能同时使用")
    elif args.query is None:
        args.random = True
    _validate(args, parser)

    requested = {item.strip().lower() for item in args.source.split(",") if item.strip()}
    valid = {
        "commons", "nasa", "loc", "archive", "pexels", "pixabay",
        "coverr", "europeana", "nps", "dvids", "all",
    }
    unknown = requested - valid
    if unknown:
        parser.error(f"未知来源：{', '.join(sorted(unknown))}")
    if "all" in requested:
        requested = valid - {"all"}

    contact = os.getenv("CRAWLER_CONTACT", "").strip()
    user_agent = (
        f"FreeVideoCrawlerBot/0.2 ({contact})"
        if contact
        else "FreeVideoCrawlerBot/0.2 (contact-not-configured)"
    )
    client = HttpClient(cache_dir=args.output / ".cache", user_agent=user_agent)
    sources = []
    if "commons" in requested:
        if not contact:
            print(
                "提示：未配置 CRAWLER_CONTACT；Wikimedia 可能使用较低限流等级。",
                file=sys.stderr,
            )
        sources.append(
            WikimediaCommonsSource(
                client,
                max_transcode_height=args.commons_max_height,
                allow_original=args.commons_original,
            )
        )
    if "nasa" in requested:
        sources.append(NasaSource(client))
    if "nps" in requested:
        key = os.getenv("NPS_API_KEY", "").strip()
        if key:
            sources.append(NpsSource(client, key))
        else:
            print("提示：未配置 NPS_API_KEY，跳过 NPS。", file=sys.stderr)
    if "dvids" in requested:
        key = os.getenv("DVIDS_API_KEY", "").strip()
        if key:
            sources.append(DvidsSource(client, key))
        else:
            print("提示：未配置 DVIDS_API_KEY，跳过 DVIDS。", file=sys.stderr)
    if "loc" in requested:
        if not contact:
            print(
                "提示：未配置 CRAWLER_CONTACT；LOC 可能拒绝未标明联系方式的自动请求。",
                file=sys.stderr,
            )
        sources.append(LibraryOfCongressSource(client))
    if "archive" in requested:
        sources.append(InternetArchiveSource(client))
    if "pexels" in requested:
        key = os.getenv("PEXELS_API_KEY", "").strip()
        if key:
            sources.append(PexelsSource(client, key))
        else:
            print("提示：未配置 PEXELS_API_KEY，跳过 Pexels。", file=sys.stderr)
    if "pixabay" in requested:
        key = os.getenv("PIXABAY_API_KEY", "").strip()
        if key:
            sources.append(PixabaySource(client, key))
        else:
            print("提示：未配置 PIXABAY_API_KEY，跳过 Pixabay。", file=sys.stderr)
    if "coverr" in requested:
        key = os.getenv("COVERR_API_KEY", "").strip()
        if key:
            sources.append(CoverrSource(client, key))
        else:
            print("提示：未配置 COVERR_API_KEY，跳过 Coverr。", file=sys.stderr)
    if "europeana" in requested:
        key = os.getenv("EUROPEANA_API_KEY", "").strip()
        if key:
            sources.append(EuropeanaSource(client, key))
        else:
            print("提示：未配置 EUROPEANA_API_KEY，跳过 Europeana。", file=sys.stderr)
    if not sources:
        parser.error("没有可用来源。请配置 API Key，或使用 --source commons、loc、archive。")

    options = CrawlOptions(
        output=args.output,
        video_dir=args.video_dir,
        limit=args.limit,
        min_width=args.min_width,
        max_width=args.max_width,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        interval=args.interval,
        commons_interval=args.commons_interval,
        metadata_only=args.metadata_only,
        max_file_mb=args.max_file_mb,
    )
    if args.random:
        try:
            pool = _load_keyword_pool(args.keyword_file)
        except ValueError as exc:
            parser.error(str(exc))
        history_path = args.output / "keyword_history.json"
        recent = [] if args.seed is not None else _load_keyword_history(history_path)
        queries = _choose_random_queries(
            pool,
            count=args.random_keywords,
            limit=args.limit,
            seed=args.seed,
            recent=recent,
        )
        print(f"随机关键词：{', '.join(queries)}")
        source_queries = _build_source_queries(
            sources,
            queries,
            count=args.random_keywords,
            limit=args.limit,
            seed=args.seed,
            recent=recent,
        )
        specialist_lines = [
            f"{name}={', '.join(values)}"
            for name, values in source_queries.items()
            if values != queries
        ]
        if specialist_lines:
            print("来源专用关键词：" + "；".join(specialist_lines))
        if args.seed is None:
            all_selected = list(dict.fromkeys(
                query for values in source_queries.values() for query in values
            ))
            _save_keyword_history(history_path, recent, all_selected)
    elif args.browse:
        sources = [source for source in sources if source.supports_browse]
        if not sources:
            parser.error("没有支持无关键词浏览的来源。请换用关键词模式。")
        queries = [""]
        source_queries = {source.name: queries for source in sources}
        print("浏览模式：遍历所选来源的全部视频（不按关键词）。")
    else:
        queries = [args.query]
        source_queries = {source.name: queries for source in sources}

    tasks = [
        (source, query)
        for source in sources
        for query in source_queries[source.name]
    ]
    quotas = _allocate(args.limit, len(tasks))
    quota_text = ", ".join(
        f"{source.name}/{query}={quota}"
        for (source, query), quota in zip(tasks, quotas)
        if quota > 0
    )
    print(f"抓取配额：{quota_text}")
    summary = CrawlSummary()
    for (source, query), quota in zip(tasks, quotas):
        if quota <= 0:
            continue
        if source.name in summary.rate_limited_sources:
            print(f"跳过已限流来源：{source.name}")
            continue
        _merge_summary(
            summary,
            crawl(query, [source], client, replace(options, limit=quota), browse=args.browse),
        )

    deficit = args.limit - summary.completed
    fallback_sources = [
        source for source in sources if source.name not in summary.rate_limited_sources
    ]
    if deficit > 0 and fallback_sources:
        fallback_tasks = [
            (source, query)
            for source in fallback_sources
            for query in source_queries[source.name]
        ]
        fallback_quotas = _allocate(deficit, len(fallback_tasks))
        print(f"补足缺额：还需 {deficit} 条，转交未限流来源再尝试一次。")
        for (source, query), quota in zip(fallback_tasks, fallback_quotas):
            if quota <= 0 or source.name in summary.rate_limited_sources:
                continue
            _merge_summary(
                summary,
                crawl(query, [source], client, replace(options, limit=quota), browse=args.browse),
            )
    print(
        f"\n完成：发现 {summary.found}，下载 {summary.downloaded}，"
        f"跳过 {summary.skipped}，失败 {summary.failed}。"
    )
    if summary.failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

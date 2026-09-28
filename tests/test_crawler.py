from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from video_crawler.crawler import CrawlOptions, crawl
from video_crawler.http import RateLimitError
from video_crawler.models import VideoAsset
from video_crawler.sources.base import VideoSource


ASSET = VideoAsset(
    source="test",
    source_id="1",
    title="Ocean / Waves",
    page_url="https://example.test/page",
    download_url="https://example.test/video.mp4",
    width=1280,
    height=720,
    duration=5,
    mime_type="video/mp4",
    author="Alice",
    author_url="https://example.test/alice",
    license_name="CC0",
    license_url="https://creativecommons.org/publicdomain/zero/1.0/",
    attribution="Ocean by Alice",
)


class FakeSource(VideoSource):
    name = "test"

    def search(self, query, **kwargs):
        yield ASSET


class FakeDownloadClient:
    def download(self, url, destination, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"video")
        return 5, "sha"


class RateLimitedClient:
    def download(self, url, destination, **kwargs):
        raise RateLimitError(url, 900, "HTTP 429")


class CrawlerTest(unittest.TestCase):
    def test_download_writes_manifest_and_credits_then_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            options = CrawlOptions(output=output, interval=0)
            first = crawl("waves", [FakeSource()], FakeDownloadClient(), options)
            second = crawl("waves", [FakeSource()], FakeDownloadClient(), options)

            self.assertEqual(first.downloaded, 1)
            self.assertEqual(second.skipped, 1)
            rows = [json.loads(line) for line in (output / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["asset"]["license_name"], "CC0")
            self.assertIn("Ocean by Alice", (output / "CREDITS.md").read_text(encoding="utf-8"))
            self.assertTrue(list((output / "videos").glob("*.mp4")))

    def test_external_video_directory_is_recorded_as_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "metadata"
            video_dir = root / "collected"
            crawl(
                "waves",
                [FakeSource()],
                FakeDownloadClient(),
                CrawlOptions(output=output, video_dir=video_dir, interval=0),
            )
            row = json.loads((output / "manifest.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(Path(row["local_path"]), next(video_dir.glob("*.mp4")).resolve())

    def test_metadata_only_does_not_download(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            summary = crawl(
                "waves",
                [FakeSource()],
                FakeDownloadClient(),
                CrawlOptions(output=output, interval=0, metadata_only=True),
            )
            self.assertEqual(summary.downloaded, 0)
            self.assertFalse((output / "videos").exists())
            self.assertIn("metadata_only", (output / "manifest.jsonl").read_text(encoding="utf-8"))

    def test_rate_limit_pauses_the_entire_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            summary = crawl(
                "waves",
                [FakeSource()],
                RateLimitedClient(),
                CrawlOptions(output=output, interval=0),
            )
            self.assertEqual(summary.downloaded, 0)
            self.assertIn("test", summary.rate_limited_sources)
            error = json.loads((output / "errors.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(error["status"], "rate_limited")
            self.assertEqual(error["retry_after_seconds"], 900)


if __name__ == "__main__":
    unittest.main()

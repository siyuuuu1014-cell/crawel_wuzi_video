from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from video_crawler.http import _redact_url, _retry_after_seconds


class HttpTest(unittest.TestCase):
    def test_redacts_api_key_without_hiding_normal_query(self) -> None:
        value = _redact_url(
            "https://example.test/api?q=forest&key=my-secret&wskey=other-secret&page=2"
        )
        self.assertNotIn("my-secret", value)
        self.assertNotIn("other-secret", value)
        self.assertIn("key=%2A%2A%2A", value)
        self.assertIn("q=forest", value)

    def test_missing_retry_after_uses_long_cooldown(self) -> None:
        self.assertEqual(_retry_after_seconds(None), 15 * 60)
        self.assertEqual(_retry_after_seconds("30"), 60)


if __name__ == "__main__":
    unittest.main()

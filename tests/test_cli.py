from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from video_crawler.cli import (
    _allocate,
    _choose_random_queries,
    _load_keyword_history,
    _load_keyword_pool,
    _save_keyword_history,
    _parser,
)


class RandomModeTest(unittest.TestCase):
    def test_default_uses_eight_random_topics(self) -> None:
        self.assertEqual(_parser().parse_args([]).random_keywords, 8)

    def test_bundled_keyword_pool_is_large_and_unique(self) -> None:
        path = Path(__file__).parents[1] / "random_keywords.txt"
        keywords = _load_keyword_pool(path)
        self.assertGreaterEqual(len(keywords), 300)
        self.assertEqual(len(keywords), len({value.casefold() for value in keywords}))

    def test_allocates_total_limit_across_keywords(self) -> None:
        self.assertEqual(_allocate(10, 3), [4, 3, 3])
        self.assertEqual(sum(_allocate(7, 5)), 7)
        self.assertEqual(sum(_allocate(100, 9)), 100)

    def test_seed_makes_selection_reproducible(self) -> None:
        pool = ["forest", "ocean", "city", "space"]
        first = _choose_random_queries(pool, count=3, limit=10, seed=42)
        second = _choose_random_queries(pool, count=3, limit=10, seed=42)
        self.assertEqual(first, second)
        self.assertEqual(len(set(first)), 3)

    def test_never_selects_more_keywords_than_video_limit(self) -> None:
        selected = _choose_random_queries(
            ["forest", "ocean", "city"], count=3, limit=1, seed=1
        )
        self.assertEqual(len(selected), 1)

    def test_keyword_file_ignores_comments_blanks_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "keywords.txt"
            path.write_text("# note\nforest\n\nForest\nocean\n", encoding="utf-8")
            self.assertEqual(_load_keyword_pool(path), ["forest", "ocean"])

    def test_recent_keywords_are_avoided_and_history_is_persisted(self) -> None:
        selected = _choose_random_queries(
            ["forest", "ocean", "city", "space"],
            count=2, limit=10, seed=2, recent=["forest", "ocean"],
        )
        self.assertEqual(set(selected), {"city", "space"})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "keyword_history.json"
            _save_keyword_history(path, ["forest"], selected)
            self.assertEqual(_load_keyword_history(path), ["forest", *selected])


if __name__ == "__main__":
    unittest.main()

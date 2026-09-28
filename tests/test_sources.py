from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from video_crawler.sources.base import choose_variant, duration_allowed
from video_crawler.sources.commons import WikimediaCommonsSource, _license_allowed
from video_crawler.sources.coverr import CoverrSource
from video_crawler.sources.dvids import DvidsSource
from video_crawler.sources.europeana import EuropeanaSource
from video_crawler.sources.internet_archive import InternetArchiveSource
from video_crawler.sources.licenses import identify_open_license
from video_crawler.sources.loc import LibraryOfCongressSource
from video_crawler.sources.pexels import PexelsSource
from video_crawler.sources.nasa import NasaSource, _choose_mp4
from video_crawler.sources.nps import NpsSource


class FakeClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[tuple] = []

    def get_json(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.payload


class SourceHelpersTest(unittest.TestCase):
    def test_choose_largest_variant_within_max_width(self) -> None:
        selected = choose_variant(
            [
                {"url": "720", "width": 1280, "height": 720},
                {"url": "1080", "width": 1920, "height": 1080},
                {"url": "4k", "width": 3840, "height": 2160},
            ],
            min_width=1000,
            max_width=1920,
        )
        self.assertEqual(selected["url"], "1080")

    def test_duration_filter(self) -> None:
        self.assertTrue(duration_allowed(8, 5, 10))
        self.assertFalse(duration_allowed(None, 5, 10))
        self.assertFalse(duration_allowed(12, 5, 10))

    def test_open_license_policy_rejects_noncommercial(self) -> None:
        self.assertIsNotNone(
            identify_open_license(url="https://creativecommons.org/licenses/by-sa/4.0/")
        )
        self.assertIsNone(
            identify_open_license(url="https://creativecommons.org/licenses/by-nc/4.0/")
        )


class CommonsSourceTest(unittest.TestCase):
    def test_rejects_noncommercial_or_no_derivatives_license(self) -> None:
        self.assertTrue(_license_allowed("CC BY-SA 4.0"))
        self.assertFalse(_license_allowed("CC BY-NC 4.0"))
        self.assertFalse(_license_allowed("CC BY-ND 4.0"))

    def test_only_emits_allowed_license(self) -> None:
        client = FakeClient(
            {
                "query": {
                    "pages": [
                        {
                            "pageid": 42,
                            "title": "File:Ocean.webm",
                            "videoinfo": [
                                {
                                    "url": "https://upload.example/Ocean.webm",
                                    "descriptionurl": "https://commons.example/Ocean.webm",
                                    "width": 1280,
                                    "height": 720,
                                    "mime": "video/webm",
                                    "derivatives": [
                                        {
                                            "src": "https://upload.example/Ocean.480p.webm",
                                            "width": 854,
                                            "height": 480,
                                            "type": "video/webm; codecs=vp9",
                                            "transcodekey": "480p.vp9.webm",
                                        }
                                    ],
                                    "extmetadata": {
                                        "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                        "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
                                        "Artist": {"value": "<b>Alice</b>"},
                                    },
                                }
                            ],
                        }
                    ]
                }
            }
        )
        assets = list(
            WikimediaCommonsSource(client).search(
                "ocean",
                limit=1,
                min_width=0,
                max_width=1920,
                min_duration=None,
                max_duration=None,
            )
        )
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].author, "Alice")
        self.assertEqual(assets[0].license_name, "CC BY-SA 4.0")
        self.assertEqual(assets[0].width, 854)
        self.assertIn("480p", assets[0].download_url)

    def test_duration_filter_returns_no_unknown_duration_assets(self) -> None:
        client = FakeClient({})
        assets = list(
            WikimediaCommonsSource(client).search(
                "ocean",
                limit=1,
                min_width=0,
                max_width=1920,
                min_duration=2,
                max_duration=None,
            )
        )
        self.assertEqual(assets, [])
        self.assertEqual(client.calls, [])


class PexelsSourceTest(unittest.TestCase):
    def test_maps_api_response_and_selects_variant(self) -> None:
        client = FakeClient(
            {
                "videos": [
                    {
                        "id": 7,
                        "duration": 9,
                        "url": "https://pexels.example/video/7",
                        "user": {"name": "Bob", "url": "https://pexels.example/bob"},
                        "video_files": [
                            {"link": "sd.mp4", "width": 640, "height": 360, "file_type": "video/mp4"},
                            {"link": "hd.mp4", "width": 1920, "height": 1080, "file_type": "video/mp4"},
                        ],
                    }
                ]
            }
        )
        assets = list(
            PexelsSource(client, "secret").search(
                "forest",
                limit=1,
                min_width=1000,
                max_width=1920,
                min_duration=3,
                max_duration=10,
            )
        )
        self.assertEqual(assets[0].download_url, "hd.mp4")
        self.assertEqual(assets[0].author, "Bob")
        self.assertEqual(client.calls[0][1]["headers"], {"Authorization": "secret"})

    def test_browse_uses_popular_endpoint_without_query(self) -> None:
        client = FakeClient({"videos": []})
        list(
            PexelsSource(client, "secret").browse(
                limit=5, min_width=0, max_width=1920,
                min_duration=None, max_duration=None,
            )
        )
        self.assertEqual(client.calls[0][0][0], "https://api.pexels.com/v1/videos/popular")
        self.assertNotIn("query", client.calls[0][1]["params"])

    def test_supports_browse_flag(self) -> None:
        self.assertTrue(PexelsSource.supports_browse)


class LibraryOfCongressSourceTest(unittest.TestCase):
    def test_requires_open_rights_and_maps_downloadable_video(self) -> None:
        client = FakeClient(
            {
                "results": [
                    {
                        "id": "http://www.loc.gov/item/abc123/",
                        "url": "https://www.loc.gov/item/abc123/",
                        "title": "Historic river",
                        "contributor": ["Example archive"],
                        "rights_advisory": ["No known restrictions on publication."],
                        "resources": [
                            {
                                "files": [[{
                                    "download": "https://tile.loc.gov/river.mp4",
                                    "mimetype": "video/mp4",
                                    "width": 1280,
                                    "height": 720,
                                    "duration": 8,
                                }]]
                            }
                        ],
                    }
                ]
            }
        )
        assets = list(
            LibraryOfCongressSource(client).search(
                "river", limit=1, min_width=1000, max_width=1920,
                min_duration=3, max_duration=10,
            )
        )
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].source_id, "abc123")
        self.assertIn("No known restrictions", assets[0].license_name)

    def test_rejects_unspecified_rights(self) -> None:
        client = FakeClient({"results": [{"id": "https://www.loc.gov/item/1/"}]})
        assets = list(
            LibraryOfCongressSource(client).search(
                "river", limit=1, min_width=0, max_width=1920,
                min_duration=None, max_duration=None,
            )
        )
        self.assertEqual(assets, [])


class MappingClient(FakeClient):
    def __init__(self, search_payload: dict, metadata_payload: dict) -> None:
        super().__init__(search_payload)
        self.metadata_payload = metadata_payload

    def get_json(self, url, **kwargs):
        self.calls.append(((url,), kwargs))
        return self.metadata_payload if "/metadata/" in url else self.payload


class InternetArchiveSourceTest(unittest.TestCase):
    def test_requires_license_url_and_prefers_small_mp4_derivative(self) -> None:
        client = MappingClient(
            {"response": {"docs": [{"identifier": "open_movie"}]}},
            {
                "metadata": {
                    "title": "Open movie",
                    "creator": "Alice",
                    "licenseurl": "https://creativecommons.org/licenses/by/4.0/",
                },
                "files": [
                    {"name": "movie.mp4", "format": "MPEG4", "size": "90000000"},
                    {"name": "movie_512kb.mp4", "format": "512Kb MPEG4", "size": "5000000"},
                ],
            },
        )
        assets = list(
            InternetArchiveSource(client).search(
                "movie", limit=1, min_width=0, max_width=1920,
                min_duration=None, max_duration=None,
            )
        )
        self.assertEqual(len(assets), 1)
        self.assertIn("movie_512kb.mp4", assets[0].download_url)
        self.assertEqual(assets[0].license_name, "CC BY 4.0")

    def test_browse_omits_keyword_from_query(self) -> None:
        client = MappingClient(
            {"response": {"docs": []}},
            {"metadata": {}, "files": []},
        )
        list(
            InternetArchiveSource(client).browse(
                limit=5, min_width=0, max_width=1920,
                min_duration=None, max_duration=None,
            )
        )
        query = client.calls[0][1]["params"]["q"]
        self.assertNotIn("AND (", query)
        self.assertIn("mediatype:movies AND licenseurl:*", query)

    def test_rejects_archive_item_without_explicit_open_license(self) -> None:
        client = MappingClient(
            {"response": {"docs": [{"identifier": "unknown"}]}},
            {"metadata": {"title": "Unknown"}, "files": [{"name": "movie.mp4"}]},
        )
        assets = list(
            InternetArchiveSource(client).search(
                "movie", limit=1, min_width=0, max_width=1920,
                min_duration=None, max_duration=None,
            )
        )
        self.assertEqual(assets, [])


class CoverrSourceTest(unittest.TestCase):
    def test_maps_signed_download_url_and_bearer_key(self) -> None:
        client = FakeClient(
            {"hits": [{
                "id": "coverr1", "title": "Forest", "duration": 6,
                "max_width": 1920, "max_height": 1080,
                "urls": {"mp4_download": "https://storage.coverr.co/forest/download?token=x"},
            }]}
        )
        assets = list(
            CoverrSource(client, "secret").search(
                "forest", limit=1, min_width=1280, max_width=1920,
                min_duration=3, max_duration=10,
            )
        )
        self.assertEqual(len(assets), 1)
        self.assertIn("download", assets[0].download_url)
        self.assertEqual(client.calls[0][1]["headers"], {"Authorization": "Bearer secret"})

    def test_browse_omits_query_param(self) -> None:
        client = FakeClient({"hits": []})
        list(
            CoverrSource(client, "secret").browse(
                limit=5, min_width=0, max_width=1920,
                min_duration=None, max_duration=None,
            )
        )
        self.assertNotIn("query", client.calls[0][1]["params"])


class EuropeanaSourceTest(unittest.TestCase):
    def test_only_maps_direct_open_video_media(self) -> None:
        client = FakeClient(
            {"items": [{
                "id": "/123/item",
                "type": "VIDEO",
                "title": ["Historic street"],
                "dcCreator": ["Museum"],
                "rights": ["http://creativecommons.org/publicdomain/mark/1.0/"],
                "edmIsShownBy": ["http://media.example/street.webm"],
                "guid": "https://www.europeana.eu/item/123/item",
            }]}
        )
        assets = list(
            EuropeanaSource(client, "secret").search(
                "street", limit=1, min_width=0, max_width=1920,
                min_duration=None, max_duration=None,
            )
        )
        self.assertEqual(len(assets), 1)
        self.assertTrue(assets[0].download_url.startswith("https://"))
        self.assertEqual(assets[0].license_name, "Public Domain Mark 1.0")
        self.assertEqual(client.calls[0][1]["params"]["reusability"], "open")


class FakeNasaClient(FakeClient):
    def get_json_list(self, url):
        return [
            "http://images-assets.nasa.gov/video/id/id~orig.mp4",
            "http://images-assets.nasa.gov/video/id/id~medium.mp4",
        ]


class NasaSourceTest(unittest.TestCase):
    def test_prefers_medium_mp4_and_maps_rights(self) -> None:
        client = FakeNasaClient(
            {
                "collection": {
                    "items": [
                        {
                            "href": "https://images-assets.nasa.gov/video/id/collection.json",
                            "data": [
                                {
                                    "nasa_id": "id",
                                    "title": "Galaxy",
                                    "center": "Goddard",
                                    "media_type": "video",
                                }
                            ],
                        }
                    ]
                }
            }
        )
        assets = list(
            NasaSource(client).search(
                "galaxy", limit=1, min_width=0, max_width=1920,
                min_duration=None, max_duration=None,
            )
        )
        self.assertEqual(len(assets), 1)
        self.assertTrue(assets[0].download_url.endswith("~medium.mp4"))
        self.assertEqual(assets[0].author, "Goddard")
        self.assertIn("NASA", assets[0].license_name)

    def test_excludes_explicit_third_party_copyright(self) -> None:
        client = FakeNasaClient(
            {
                "collection": {
                    "items": [
                        {
                            "href": "https://example.test/manifest.json",
                            "data": [{"nasa_id": "protected", "copyright": "Third Party"}],
                        }
                    ]
                }
            }
        )
        assets = list(
            NasaSource(client).search(
                "space", limit=1, min_width=0, max_width=1920,
                min_duration=None, max_duration=None,
            )
        )
        self.assertEqual(assets, [])

    def test_mp4_choice_is_https_and_bandwidth_conscious(self) -> None:
        selected = _choose_mp4(
            [
                "http://example.test/video~orig.mp4",
                "http://example.test/video~small.mp4",
            ]
        )
        self.assertEqual(selected, "https://example.test/video~small.mp4")


class DvidsClient(FakeClient):
    def __init__(self) -> None:
        super().__init__({})

    def get_json(self, url, **kwargs):
        self.calls.append(((url,), kwargs))
        if url.endswith("/search"):
            return {"results": [{"id": "video:42"}]}
        return {"results": {
            "id": "video:42", "title": "Rescue training", "duration": 12,
            "url": "https://www.dvidshub.net/video/42/rescue-training",
            "credit": [{"rank": "Sgt.", "name": "Alice", "url": "https://example.test/alice"}],
            "files": [
                {"src": "https://example.test/720.mp4", "type": "video/mp4", "width": 1280, "height": 720},
                {"src": "https://example.test/1080.mp4", "type": "video/mp4", "width": 1920, "height": 1080},
            ],
        }}


class DvidsSourceTest(unittest.TestCase):
    def test_searches_video_details_and_maps_public_use_notice(self) -> None:
        client = DvidsClient()
        assets = list(DvidsSource(client, "secret").search(
            "rescue", limit=1, min_width=1000, max_width=1920,
            min_duration=5, max_duration=20,
        ))
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].source_id, "42")
        self.assertEqual(assets[0].download_url, "https://example.test/1080.mp4")
        self.assertIn("DVIDS", assets[0].license_name)
        self.assertEqual(client.calls[0][1]["params"]["api_key"], "secret")


class NpsSourceTest(unittest.TestCase):
    def test_maps_official_video_versions_and_api_header(self) -> None:
        client = FakeClient({"data": [{
            "id": "abc", "title": "Bison", "durationMs": 8000,
            "credit": "NPS/Jane Doe", "permalinkUrl": "https://www.nps.gov/video/abc",
            "versions": [
                {"url": "http://example.test/360.mp4", "fileType": "video/mp4", "widthPixels": 640, "heightPixels": 360},
                {"url": "http://example.test/720.mp4", "fileType": "video/mp4", "widthPixels": 1280, "heightPixels": 720},
            ],
        }]})
        assets = list(NpsSource(client, "secret").search(
            "bison", limit=1, min_width=1000, max_width=1920,
            min_duration=5, max_duration=10,
        ))
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].download_url, "https://example.test/720.mp4")
        self.assertEqual(assets[0].duration, 8)
        self.assertEqual(client.calls[0][1]["headers"], {"X-Api-Key": "secret"})

    def test_rejects_explicit_third_party_notice(self) -> None:
        client = FakeClient({"data": [{
            "id": "protected", "title": "Courtesy of Third Party",
            "versions": [{"url": "https://example.test/x.mp4", "fileType": "video/mp4", "widthPixels": 1280}],
        }]})
        assets = list(NpsSource(client, "secret").search(
            "forest", limit=1, min_width=0, max_width=1920,
            min_duration=None, max_duration=None,
        ))
        self.assertEqual(assets, [])


if __name__ == "__main__":
    unittest.main()

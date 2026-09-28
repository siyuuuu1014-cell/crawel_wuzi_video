from __future__ import annotations


# Specialist collections perform much better with vocabulary suited to their catalogues.
# General stock sources continue to use random_keywords.txt.
SOURCE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "nasa": (
        "earth from space", "moon surface", "mars mission", "rocket launch",
        "astronaut training", "space station", "satellite orbit", "solar activity",
        "galaxy stars", "space science", "mission control", "aerial earth",
    ),
    "nps": (
        "mountain landscape", "forest wildlife", "ocean coast", "desert landscape",
        "waterfall river", "night sky", "wildflowers", "bison wildlife",
        "bird migration", "park ranger", "historic site", "hiking trail",
        "volcano geology", "glacier", "wetlands", "underwater nature",
    ),
    "dvids": (
        "aircraft", "helicopter", "ship at sea", "search and rescue",
        "disaster response", "humanitarian assistance", "medical training",
        "firefighting", "engineering", "logistics", "parachute training",
        "coast guard", "military exercise", "ceremony", "weather operations",
        "aerial footage",
    ),
    "loc": (
        "historic city", "early cinema", "railroad history", "industrial history",
        "street scene", "agriculture history", "American history", "historic parade",
        "factory workers", "historic travel", "folk culture", "newsreel",
    ),
    "archive": (
        "public domain nature", "public domain travel", "historic film",
        "educational film", "city documentary", "science documentary",
        "open source animation", "public domain space", "wildlife documentary",
        "cultural heritage", "experimental film", "archival footage",
    ),
}


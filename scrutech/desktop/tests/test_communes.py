"""The commune lookup: what the API answers must become a usable study area."""

from scrutech_desktop import communes

_ANSWER = [
    {
        "nom": "Lyon",
        "code": "69123",
        "population": 522250,
        "departement": {"nom": "Rhône"},
        "contour": {
            "type": "Polygon",
            "coordinates": [[[4.77, 45.70], [4.90, 45.70], [4.90, 45.81], [4.77, 45.81]]],
        },
    },
    {"nom": "Sans contour", "code": "00000", "population": 1},
]


def test_parse_keeps_only_communes_with_an_outline():
    found = communes.parse(_ANSWER)
    assert [c.name for c in found] == ["Lyon"]
    assert "Rhône" in found[0].label


def test_bbox_is_west_south_east_north():
    assert communes.parse(_ANSWER)[0].bbox() == (4.77, 45.70, 4.90, 45.81)


def test_bbox_of_a_multipolygon():
    island = communes.parse(
        [
            {
                "nom": "Deux morceaux",
                "code": "1",
                "population": 2,
                "departement": {"nom": "Ailleurs"},
                "contour": {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [[[1.0, 1.0], [2.0, 1.0], [2.0, 2.0]]],
                        [[[5.0, 0.5], [6.0, 0.5], [6.0, 3.0]]],
                    ],
                },
            }
        ]
    )[0]
    assert island.bbox() == (1.0, 0.5, 6.0, 3.0)

import pytest
from shapely.geometry import LineString

from vectormaps.labels import parse_langs, pick_name, street_pieces, text_width


def test_pick_name_prefers_the_language_then_the_mapped_name():
    tags = {"name": "Santiago", "name:es": "Santiago", "name:gl": "Compostela", "name:en": "St"}
    assert pick_name(tags, ["gl"]) == "Compostela"
    assert pick_name(tags, ["ja", "en"]) == "St"  # the first language that has one
    assert pick_name(tags, ["ja"]) == "Santiago"  # none: as mapped
    assert pick_name(tags, ["local", "gl"]) == "Compostela"  # local is not a language
    assert pick_name({"highway": "primary"}, ["es"]) is None


def test_parse_langs():
    assert parse_langs("es") == ["es"]
    assert parse_langs("gl, es") == ["gl", "es"]
    assert parse_langs("zh-Hans,local") == ["zh-Hans", "local"]
    for bad in ("", "español", "e", "es;en"):
        with pytest.raises(ValueError, match="language"):
            parse_langs(bad)


def test_street_pieces_read_left_to_right_and_skip_short_streets():
    size, text = 1.5, "Calle Larga"
    w = text_width(text, size)
    long_street = LineString([(100, 50), (0, 50)])  # drawn right to left
    (piece,) = street_pieces([long_street], text, size)
    assert piece.coords[0][0] < piece.coords[-1][0]
    assert piece.length >= w
    assert street_pieces([LineString([(0, 0), (w / 2, 0)])], text, size) == []


def test_ways_of_one_street_are_joined_and_labelled_once_per_stretch():
    size, text = 1.5, "Calle Larga"
    w = text_width(text, size)
    # Three ways that, joined, are one street of 2.5 label widths.
    xs = [0, w, 2 * w, 2.5 * w]
    ways = [LineString([(a, 0), (b, 0)]) for a, b in zip(xs, xs[1:], strict=False)]
    assert len(street_pieces(ways, text, size)) == 1
    # A very long street gets the name repeated.
    assert len(street_pieces([LineString([(0, 0), (w * 20, 0)])], text, size)) == 3


def test_a_curly_street_is_not_labelled():
    curly = LineString([(0, 0), (5, 5), (0, 10), (5, 15), (0, 20), (5, 25), (0, 30)])
    assert street_pieces([curly], "Calle", 2.0) == []

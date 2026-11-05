import pytest
from shapely.geometry import LineString, box

from vectormaps.labels import (
    LABEL_EVERY,
    SLOT_SHIFTS,
    Placer,
    parse_langs,
    pick_name,
    street_pieces,
    street_slots,
    text_width,
)


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
    # zigzags much shorter than the name: every piece the name could go on curls
    curly = LineString([(x % 2 * 2, x * 2) for x in range(16)])
    assert street_pieces([curly], "Calle", 2.0) == []
    assert street_slots([curly], "Calle", 2.0) == []


def test_a_slot_offers_other_pieces_along_the_line_middle_first():
    street = LineString([(0, 0), (200, 0)])
    width = text_width("Rúa", 2.0)
    slots = street_slots([street], "Rúa", 2.0)
    assert len(slots) == int(200 // (width * LABEL_EVERY))
    room = 200 / len(slots)
    for i, pieces in enumerate(slots):
        middles = [p.interpolate(0.5, normalized=True).x for p in pieces]
        assert middles[0] == pytest.approx(room * (i + 0.5))
        assert len(pieces) == len(SLOT_SHIFTS)
        assert all(abs(m - middles[0]) < room / 2 for m in middles)  # in its own room


def test_the_placer_keeps_the_first_and_refuses_what_overlaps_it():
    placer = Placer([box(90, 90, 100, 100)])
    assert placer.take(box(0, 0, 10, 2))
    assert not placer.take(box(5, 1, 15, 3))  # overlaps the first
    assert placer.take(box(11, 0, 20, 2))  # beside it
    assert not placer.take(box(95, 95, 96, 96))  # what it was given to start with
    assert placer.free(box(30, 30, 31, 31))


@pytest.mark.parametrize("ratio", [1.25, 1.3, 1.39, 1.4, 2.0])
def test_a_street_just_long_enough_gets_the_whole_name_not_a_sliver(ratio):
    width = text_width("Autopista del Atlántico", 2.0)
    street = LineString([(0, 0), (width * ratio, 0)])
    pieces = street_pieces([street], "Autopista del Atlántico", 2.0)
    assert len(pieces) == 1
    assert pieces[0].length >= width


def test_a_name_does_not_go_on_a_sharp_elbow_of_the_line():
    # Nov 5: "Río Anllóns" was written on a 58° bend (length / chord 1.23, under
    # MAX_WIGGLE) and its letters piled up on the inside of it.
    text, size = "Río Anllóns", 2.6
    elbow = LineString([(58.07, 150.67), (57.63, 143.51), (61.02, 136.9), (68.35, 136.25)])
    assert street_pieces([elbow], text, size) == []
    gentle = LineString([(0, 0), (12, 2), (24, 5)])  # a 6° bend: still fine
    assert len(street_pieces([gentle], text, size)) == 1

"""Names that do not overlap: the order they win in, and where the losers go."""

import itertools
import xml.etree.ElementTree as ET

import pytest
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon

from vectormaps.area import fit
from vectormaps.layers import LABEL_PRIORITY, LAYERS, select
from vectormaps.pipeline import Item
from vectormaps.render import (
    LINE_HALF_HEIGHT,
    POINT_GAP,
    POINT_SHIFTS,
    Job,
    _north_box,
    _place_box,
    render,
)
from vectormaps.theme import load

NS = {"svg": "http://www.w3.org/2000/svg"}
HREF = "{http://www.w3.org/1999/xlink}href"
TL, BR = (42.8845, -8.5510), (42.8775, -8.5385)
FRAME = fit(TL, BR, "A4", orientation="landscape")
NAMES = ["places", "street-names", "water-names", "green-names"]


def at(x: float, y: float, frame=FRAME) -> tuple[float, float]:
    """(lon, lat) of a point given in page mm."""
    back = Transformer.from_crs(frame.crs, 4326, always_xy=True)
    mpm = frame.metres_per_mm
    return back.transform(
        frame.xmin + (x - frame.map_x) * mpm, frame.ymax - (y - frame.map_y) * mpm
    )


def point(x, y):
    return Point(*at(x, y))


def line(*xys):
    return LineString([at(x, y) for x, y in xys])


def polygon(*xys):
    return Polygon([at(x, y) for x, y in xys])


def draw(feats, theme="color", frame=FRAME):
    job = Job("a", frame, load(theme), select([n for n in NAMES if n in feats]), feats)
    return job, ET.fromstring(render([job]))


def _layer_of(group_id: str) -> tuple[str, str]:
    rest = group_id.removeprefix("a-")
    name = max((n for n in LAYERS if rest.startswith(n + "-")), key=len)
    return name, rest[len(name) + 1 :]


def labels(job, root) -> list[tuple[str, str, object]]:
    """(layer, text, the room it takes) of every name drawn, as the placer sees it."""
    paths = {p.get("id"): p for p in root.findall(".//svg:defs/svg:path", NS)}
    out = []
    for g in root.findall(".//svg:g[@class]", NS):
        if not g.get("id", "").startswith("a-") or g.get("id") == "a-north":
            continue
        name, cls = _layer_of(g.get("id"))
        if not LAYERS[name].text:
            continue
        style = job.theme.style(name, cls)
        for t in g.findall("svg:text", NS):
            tp = t.find("svg:textPath", NS)
            if tp is None:
                shape = _place_box(float(t.get("x")), float(t.get("y")), t.text, style)
                out.append((f"{name}.{cls}", t.text, shape))
                continue
            nums = [float(v) for v in paths[tp.get(HREF)[1:]].get("d").removeprefix("M").split()]
            piece = LineString(list(zip(nums[::2], nums[1::2], strict=True)))
            room = LINE_HALF_HEIGHT * style["font-size"] + style["stroke-width"] / 2
            out.append((f"{name}.{cls}", tp.text, piece.buffer(room, cap_style="flat")))
    return out


def assert_no_overlap(found):
    for (_, a, sa), (_, b, sb) in itertools.combinations(found, 2):
        # touching edges are fine; sharing any room is not (0.01 mm² for the rounding)
        assert sa.intersection(sb).area < 0.01, f"{a!r} overlaps {b!r}"


def texts(root, group):
    return [
        (t.text, float(t.get("x")), float(t.get("y")))
        for t in root.findall(f".//svg:g[@id='a-{group}']/svg:text", NS)
    ]


def test_every_label_class_has_a_priority_and_every_priority_a_class():
    classes = {(n, c) for n, layer in LAYERS.items() if layer.text for c in layer.classes}
    assert set(LABEL_PRIORITY) == classes
    assert len(LABEL_PRIORITY) == len(classes)


def test_a_hamlet_is_over_a_neighbourhood_even_if_it_comes_second():
    # O Couto (a hamlet) and O Lugar da Fonte (a neighbourhood in it), Nov 5: the
    # neighbourhood came first from OSM and was drawn over the hamlet.
    feats = {
        "places": [
            Item("suburb", point(150, 100), "O Lugar da Fonte", rank=6),
            Item("hamlet", point(146, 100), "O Couto", rank=3),
        ]
    }
    job, root = draw(feats, "vintage")
    assert texts(root, "places-hamlet") == [("O Couto", pytest.approx(146), pytest.approx(100))]
    ((name, x, y),) = texts(root, "places-suburb")  # moved over or under its point, not dropped
    style = job.theme.style("places", "suburb")
    box = _place_box(0, 0, name, style).bounds
    step = box[3] - box[1] + POINT_GAP * style["font-size"]
    assert name == "O Lugar da Fonte" and x == pytest.approx(150)
    assert y in [pytest.approx(100 + s * step, abs=0.01) for s in POINT_SHIFTS[1:]]
    assert_no_overlap(labels(job, root))


def test_a_hamlet_is_bigger_than_a_neighbourhood_and_smaller_than_a_village():
    for name in ("bw", "color", "vintage", "vintage-bw", "dark", "street", "poster", "blueprint"):
        theme = load(name)
        size = {c: theme.style("places", c)["font-size"] for c in ("suburb", "hamlet", "village")}
        assert size["suburb"] < size["hamlet"] < size["village"], name


def test_in_its_class_a_suburb_goes_before_a_quarter_before_a_neighbourhood():
    layer = LAYERS["places"]
    ranks = {
        v: layer.match("point", {"place": v, "name": "X"})
        for v in ("suburb", "quarter", "neighbourhood", "hamlet")
    }
    assert ranks["hamlet"][0] == "hamlet"
    assert {ranks[v][0] for v in ("suburb", "quarter", "neighbourhood")} == {"suburb"}
    assert ranks["suburb"][1] < ranks["quarter"][1] < ranks["neighbourhood"][1]
    feats = {
        "places": [
            Item("suburb", point(150, 100), "Barrio", rank=ranks["neighbourhood"][1]),
            Item("suburb", point(150, 100), "Arrabal", rank=ranks["suburb"][1]),
        ]
    }
    _, root = draw(feats)
    first, *_ = texts(root, "places-suburb")
    assert first == ("Arrabal", pytest.approx(150), pytest.approx(100))


def test_a_place_with_no_room_left_is_left_out():
    feats = {"places": [Item("village", point(150, 100), f"Aldea {n}") for n in range(5)]}
    job, root = draw(feats)
    found = texts(root, "places-village")
    assert len(found) == len(POINT_SHIFTS)  # on the point, over it, under it; no more
    assert_no_overlap(labels(job, root))


def test_places_win_over_streets_and_the_street_name_moves_along_the_street():
    feats = {
        "street-names": [Item("major", line((20, 100), (260, 100)), "Avenida de Lugo")],
        "places": [Item("village", point(140, 100), "Sar")],
    }
    job, root = draw(feats)
    assert [t for t, *_ in texts(root, "places-village")] == ["Sar"]  # on its point
    found = labels(job, root)
    assert any(text == "Avenida de Lugo" for _, text, _ in found)  # still written
    assert_no_overlap(found)


def test_water_and_parks_win_over_streets_and_streams_lose_to_them():
    order = [f"{n}.{c}" for n, c in LABEL_PRIORITY]
    places = [o for o in order if o.startswith("places.")]
    nature = ["water-names.lake", "water-names.river", "green-names.park", "green-names.reserve"]
    streets = [o for o in order if o.startswith("street-names.")]
    assert order == [*places, *nature, *streets, "water-names.stream"]


def test_a_lake_is_named_inside_it_and_a_park_too_small_for_its_name_is_not():
    lake = polygon((60, 60), (200, 60), (200, 140), (60, 140))
    feats = {
        "water-names": [Item("lake", lake, "Encoro de Cecebre")],
        "green-names": [
            Item("park", polygon((230, 150), (232, 150), (232, 152), (230, 152)), "Parque grande"),
            Item("park", polygon((220, 20), (270, 20), (270, 50), (220, 50)), "Alameda"),
        ],
    }
    job, root = draw(feats)
    ((name, x, y),) = texts(root, "water-names-lake")
    assert name == "Encoro de Cecebre" and 60 < x < 200 and 60 < y < 140
    assert [t for t, *_ in texts(root, "green-names-park")] == ["Alameda"]
    for _, _, shape in labels(job, root):
        assert shape.within(Polygon([(60, 60), (200, 60), (200, 140), (60, 140)]).buffer(2)) or (
            shape.within(Polygon([(220, 20), (270, 20), (270, 50), (220, 50)]).buffer(2))
        )


def test_a_river_is_named_along_it_and_a_stream_gives_way_to_a_street():
    feats = {
        "water-names": [
            Item("river", line((20, 80), (260, 80)), "Río Mero"),
            Item("stream", line((20, 120), (260, 120)), "Rego da Fonte"),
        ],
        "street-names": [Item("minor", line((20, 120), (260, 120)), "Rúa da Ponte")],
    }
    job, root = draw(feats, "vintage")
    found = labels(job, root)
    assert {t for _, t, _ in found} >= {"Río Mero", "Rúa da Ponte"}
    assert_no_overlap(found)
    river = job.theme.style("water-names", "river")
    assert river["font-style"] == "italic" and "text-anchor" not in river


def test_no_name_goes_under_the_north_arrow():
    arrow = _north_box(FRAME)
    x, y = arrow.centroid.x, arrow.centroid.y
    feats = {"places": [Item("village", point(x, y), "Norte"), Item("town", point(x, y), "Arriba")]}
    job, root = draw(feats)
    for _, _, shape in labels(job, root):
        assert not shape.intersects(arrow)


def test_a_crowded_map_has_no_two_names_on_top_of_each_other():
    places = [
        Item(cls, point(30 + 23 * i + (j % 2) * 9, 25 + 14 * j), f"Lugar {i}-{j}", rank=r)
        for i in range(10)
        for j in range(11)
        for cls, r in [(("village", 2), ("hamlet", 3), ("suburb", 6))[(i + j) % 3]]
    ]
    streets = [
        Item(
            ("major", "secondary", "minor")[k % 3],
            line((10, 12 + 17 * k), (280, 18 + 17 * k)),
            f"Rúa número {k}",
        )
        for k in range(11)
    ] + [
        Item("minor", line((12 + 25 * k, 10), (20 + 25 * k, 200)), f"Travesía {k}")
        for k in range(11)
    ]
    feats = {
        "places": places,
        "street-names": streets,
        "water-names": [
            Item("river", line((10, 150), (140, 110), (280, 160)), "Río Sar"),
            Item("lake", polygon((150, 130), (230, 130), (230, 190), (150, 190)), "Lagoa"),
        ],
        "green-names": [
            Item("park", polygon((20, 160), (90, 160), (90, 195), (20, 195)), "Carballeira"),
        ],
    }
    job, root = draw(feats, "vintage")
    found = labels(job, root)
    assert len(found) > 60  # still a well-labelled map
    assert_no_overlap(found)
    kinds = {k for k, _, _ in found}
    assert {"places.village", "places.hamlet", "water-names.lake", "street-names.major"} <= kinds

import dataclasses
import xml.etree.ElementTree as ET

import pytest
from shapely.geometry import LineString, Point, Polygon

from vectormaps.area import fit
from vectormaps.labels import CHAR_WIDTH
from vectormaps.layers import select
from vectormaps.pipeline import Item
from vectormaps.render import (
    CAP_HEIGHT,
    MARK,
    Job,
    _corner,
    _num,
    legend_lines,
    path_data,
    render,
    true_north,
)
from vectormaps.theme import load

NS = {"svg": "http://www.w3.org/2000/svg", "ink": "http://www.inkscape.org/namespaces/inkscape"}
LABEL = "{http://www.inkscape.org/namespaces/inkscape}label"
SVG_G = "{http://www.w3.org/2000/svg}g"


def square(lon, lat, d):
    return Polygon([(lon, lat), (lon + d, lat), (lon + d, lat + d), (lon, lat + d)])


def make_job(label, tl, br, theme, opacity=1.0):
    frame = fit(tl, br, "A4", orientation="landscape")
    cx = (tl[1] + br[1]) / 2
    cy = (tl[0] + br[0]) / 2
    feats = {
        "buildings": [Item("building", square(cx - 0.0005, cy - 0.0005, 0.001))],
        # Longer than the page, so it has to be clipped.
        "roads": [Item("minor", LineString([(tl[1] - 0.01, cy), (br[1] + 0.01, cy)]))],
    }
    return Job(label, frame, load(theme), select(["buildings", "roads"]), feats, opacity)


TL, BR = (42.8845, -8.5510), (42.8775, -8.5385)
TL2, BR2 = (42.8830, -8.5470), (42.8815, -8.5440)


def test_path_data():
    assert path_data([Polygon([(0, 0), (10, 0), (10, 10)])]) == "M0 0 10 0 10 10Z"
    assert path_data([LineString([(0, 0), (1.234, 5)])]) == "M0 0 1.23 5"
    assert path_data([Polygon([(0, 0), (0.01, 0), (0, 0.01)])]) == ""  # a speck


def test_single_area_svg():
    root = ET.fromstring(render([make_job("a", TL, BR, "color")]))
    assert root.get("width") == "297mm" and root.get("height") == "210mm"
    assert root.get("viewBox") == "0 0 297 210"
    labels = [g.get(LABEL) for g in root.iter(SVG_G)]
    assert {"page", "frame", "buildings", "roads"} <= set(labels)
    assert root.find(".//svg:path[@id='a-buildings-building']", NS) is not None
    assert "OpenStreetMap contributors" in "".join(root.itertext())


def test_everything_stays_inside_the_frame():
    job = make_job("a", TL, BR, "color")
    svg = render([job])
    road = ET.fromstring(svg).find(".//svg:path[@id='a-roads-minor']", NS).get("d")
    xs = [float(v) for v in road.removeprefix("M").split()[::2]]
    assert min(xs) == pytest.approx(job.frame.margin, abs=0.01)
    assert max(xs) == pytest.approx(job.frame.page_w - job.frame.margin, abs=0.01)


def test_overlay_stacks_two_scales_in_one_page():
    a = make_job("a", TL, BR, "color")
    b = make_job("b", TL2, BR2, "bw", opacity=0.6)
    root = ET.fromstring(render([a, b]))
    ids = [g.get("id") for g in root.findall("svg:g", NS)]
    assert ids == ["page", "area-a", "area-b", "north", "frame", "legend"]  # b over a
    assert root.find("svg:g[@id='area-b']", NS).get("opacity") == "0.6"
    assert root.find("svg:g[@id='area-a']", NS).get("opacity") is None
    assert a.frame.scale > b.frame.scale
    text = "".join(root.itertext())
    assert f"A 1:{a.frame.scale}" in text and f"B 1:{b.frame.scale}" in text
    # The same building is bigger on the zoomed area.
    pa = root.find(".//svg:path[@id='a-buildings-building']", NS).get("d")
    pb = root.find(".//svg:path[@id='b-buildings-building']", NS).get("d")
    assert pa != pb


def test_empty_layers_still_exist():
    job = make_job("a", TL, BR, "bw")
    job.features = {}
    root = ET.fromstring(render([job]))
    assert root.find(".//svg:g[@id='a-roads']", NS) is not None
    assert root.find(".//svg:g[@id='area-a']//svg:path", NS) is None


def test_labels_are_text_on_the_street_and_at_the_place():
    frame = fit(TL, BR, "A4", orientation="landscape")
    cy = (TL[0] + BR[0]) / 2
    cx = (TL[1] + BR[1]) / 2
    feats = {
        "street-names": [
            Item("major", LineString([(TL[1], cy), (BR[1], cy)]), "Rúa do Vilar & Co"),
        ],
        "places": [
            Item("village", Point(cx, cy + 0.001), "A Almáciga"),
            Item("city", Point(cx + 5, cy), "Fuera del marco"),  # outside the map: dropped
        ],
    }
    job = Job("a", frame, load("color"), select(["street-names", "places"]), feats)
    root = ET.fromstring(render([job]))
    path_id = root.find(".//svg:textPath", NS).get("{http://www.w3.org/1999/xlink}href")[1:]
    assert root.find(f".//svg:defs/svg:path[@id='{path_id}']", NS) is not None
    assert "Rúa do Vilar & Co" in "".join(root.find(".//svg:textPath", NS).itertext())
    texts = [t.text for t in root.findall(".//svg:g[@id='a-places-village']/svg:text", NS)]
    assert texts == ["A Almáciga"]
    assert root.find(".//svg:g[@id='a-places-city']", NS) is None
    assert root.find(".//svg:g[@id='a-places-village']", NS).get("text-anchor") == "middle"


def test_legend_has_the_corners_the_attribution_and_the_mark():
    job = make_job("a", TL, BR, "color")
    root = ET.fromstring(render([job]))
    texts = [t.text for t in root.findall(".//svg:g[@id='legend']/svg:text", NS)]
    tl, br = job.frame.corners()
    # all in one line, in the order of the minimal one, with the paper before the credit
    corners = f"↖ {tl[0]:.5f}, {tl[1]:.5f} · ↘ {br[0]:.5f}, {br[1]:.5f}"
    scale = f"1:{job.frame.scale}"
    assert texts[0] == f"{corners} · {scale} · A4 landscape · © OpenStreetMap contributors (ODbL)"
    assert texts[1:] == ["Generated with vector-maps by 1noro"]
    # The corners are the ones of the map on paper (it grew to the shape of the page).
    assert tl[0] >= TL[0] and br[0] <= BR[0] and tl[1] <= TL[1] and br[1] >= BR[1]


def test_minimal_legend_keeps_the_corners_the_scale_the_credit_and_the_mark():
    job = make_job("a", TL, BR, "color")
    root = ET.fromstring(render([job], "minimal"))
    texts = [t.text for t in root.findall(".//svg:g[@id='legend']/svg:text", NS)]
    tl, br = job.frame.corners()
    corners = f"↖ {tl[0]:.5f}, {tl[1]:.5f} · ↘ {br[0]:.5f}, {br[1]:.5f}"
    assert texts == [f"{corners} · 1:{job.frame.scale} · © OpenStreetMap", MARK]
    with pytest.raises(ValueError, match="unknown legend"):
        render([job], "none")


def test_overlay_legend_lists_both_zones():
    a = make_job("a", TL, BR, "color")
    b = make_job("b", TL2, BR2, "bw")
    (line,) = legend_lines([a, b])
    assert line.startswith("A: ↖ ") and "   |   B: ↖ " in line
    assert " · A 1:" in line and " + B 1:" in line


@pytest.mark.parametrize("legend", ["full", "minimal"])
@pytest.mark.parametrize("paper,margin", [("A5", 6), ("A5", 10), ("A0", 6)])
def test_legend_text_stays_inside_the_page(paper, margin, legend):
    frame = fit(TL, BR, paper, margin=margin)
    a = Job("a", frame, load("bw"), select(["roads"]), {})
    b = Job("b", fit(TL2, BR2, paper, margin, frame.orientation), load("bw"), [], {})
    root = ET.fromstring(render([a, b], legend))
    size = float(root.find(".//svg:g[@id='legend']/svg:text", NS).get("font-size"))
    for t in root.findall(".//svg:g[@id='legend']/svg:text", NS):
        y = float(t.get("y"))
        assert 0 < y < frame.page_h
        if t.get("text-anchor") != "end":
            assert len(t.text) * size * CHAR_WIDTH <= frame.map_w + 0.01  # fits the width
    last = max(float(t.get("y")) for t in root.findall(".//svg:g[@id='legend']/svg:text", NS))
    assert last + size * 0.3 <= frame.page_h  # the bottom line does not run off the paper


def _shaped_job(shape):
    frame = fit(TL, BR, "A4", orientation="landscape", shape=shape)
    feats = {"roads": [Item("minor", LineString([(TL[1], 42.881), (BR[1], 42.881)]))]}
    return Job("a", frame, load("color"), select(["roads"]), feats)


def test_circle_is_clipped_and_outlined():
    svg = render([_shaped_job("circle")])
    root = ET.fromstring(svg)
    clip = root.find(".//svg:clipPath[@id='clip-a']/svg:circle", NS)
    assert clip is not None and float(clip.get("r")) == pytest.approx(95)  # 190 mm wide
    assert (float(clip.get("cx")), float(clip.get("cy"))) == pytest.approx((148.5, 105))
    area = root.find(".//svg:g[@id='area-a']", NS)
    assert area.get("clip-path") == "url(#clip-a)"
    frame = root.find(".//svg:g[@id='frame']/svg:circle", NS)
    assert frame is not None and frame.get("fill") == "none"


@pytest.mark.parametrize("shape", ["rect", "square"])
def test_rect_and_square_are_clipped_to_the_map_and_have_a_rect_outline(shape):
    # Clipped too: a round line end at the edge would reach past the frame.
    job = _shaped_job(shape)
    root = ET.fromstring(render([job]))
    clip = root.find(".//svg:clipPath[@id='clip-a']/svg:rect", NS)
    f = job.frame
    box = [float(clip.get(k)) for k in ("x", "y", "width", "height")]
    assert box == pytest.approx([f.map_x, f.map_y, f.map_w, f.map_h], abs=0.01)
    assert root.find(".//svg:g[@id='area-a']", NS).get("clip-path") == "url(#clip-a)"
    outline = root.find(".//svg:g[@id='frame']/svg:rect", NS)
    w = float(outline.get("width"))
    assert w == pytest.approx(277 if shape == "rect" else 190)


def test_circle_legend_gives_the_centre_instead_of_the_corners():
    job = _shaped_job("circle")
    lat, lon = job.frame.center()
    assert lat == pytest.approx((TL[0] + BR[0]) / 2, abs=1e-4)
    assert lon == pytest.approx((TL[1] + BR[1]) / 2, abs=1e-4)
    full = legend_lines([job])
    assert full[0].startswith(f"⌖ {lat:.5f}, {lon:.5f} · 1:")
    assert "↖" not in "".join(full) and "↘" not in "".join(full)
    assert legend_lines([job], "minimal")[0].startswith(f"⌖ {lat:.5f}, {lon:.5f} · 1:")
    square = legend_lines([_shaped_job("square")])
    assert "↖" in square[0]  # only the circle changes


@pytest.mark.parametrize(
    "coords, expected",
    [
        ("dd", "42.88000, -8.54000"),
        ("dm", "42°52.800'N 8°32.400'W"),
        ("dms", "42°52'48.0\"N 8°32'24.0\"W"),
    ],
)
def test_coordinate_formats(coords, expected):
    assert _corner((42.88, -8.54), coords) == expected


def test_coordinate_formats_carry_and_hemispheres():
    # 59.99996' rounds up into the next degree instead of writing 60.000'
    assert _corner((10.99999999, 0.0), "dm") == "11°00.000'N 0°00.000'E"
    assert _corner((-33.5, 151.25), "dms") == "33°30'00.0\"S 151°15'00.0\"E"
    assert _corner((0.9999999, 0.0), "dms") == "1°00'00.0\"N 0°00'00.0\"E"


def test_legend_uses_the_chosen_coordinate_format():
    job = make_job("a", TL, BR, "color")
    for coords in ("dm", "dms"):
        lines = legend_lines([job], "full", coords)
        assert "↖" in lines[0] and "°" in lines[0] and "." in lines[0]
        assert "°" in legend_lines([job], "minimal", coords)[0]
        assert "°" in render([job], "full", coords)
    assert "°" not in legend_lines([job])[0]  # decimal degrees by default
    with pytest.raises(ValueError, match="coordinate format"):
        legend_lines([job], "full", "utm")
    circle = legend_lines([_shaped_job("circle")], "full", "dms")
    assert circle[0].startswith("⌖ 42°") and "N" in circle[0]


def test_a_casing_is_a_wider_line_under_every_line_of_the_layer():
    root = ET.fromstring(render([make_job("a", TL, BR, "street")]))
    roads = root.find(".//svg:g[@id='a-roads']", NS)
    ids = [p.get("id") for p in roads]
    assert ids == ["a-roads-minor-casing", "a-roads-minor"]
    casing, line = list(roads)
    assert casing.get("d") == line.get("d")
    style = load("street").style("roads", "minor")
    wider = style["stroke-width"] + 2 * style["casing-width"]
    assert float(casing.get("stroke-width")) == pytest.approx(wider)
    assert casing.get("stroke") == style["casing-color"] and casing.get("fill") == "none"
    # The casing keys are not SVG attributes: they stay out of the drawing.
    assert line.get("casing-width") is None and line.get("casing-color") is None


def test_a_see_through_casing_is_a_band_under_a_solid_line():
    job = make_job("a", TL, BR, "street")
    minor = {**job.theme.style("roads", "minor"), "casing-opacity": 0.3}
    layers = {**job.theme.layers, "roads": {**job.theme.layers["roads"], "minor": minor}}
    job = dataclasses.replace(job, theme=dataclasses.replace(job.theme, layers=layers))
    casing, line = ET.fromstring(render([job])).find(".//svg:g[@id='a-roads']", NS)
    assert casing.get("stroke-opacity") == "0.3"
    assert line.get("stroke-opacity") is None and line.get("casing-opacity") is None


def test_no_casing_where_the_theme_has_none():
    root = ET.fromstring(render([make_job("a", TL, BR, "bw")]))
    assert root.find(".//svg:path[@id='a-roads-minor-casing']", NS) is None


def _defs_xy(root):
    for p in root.findall(".//svg:defs/svg:path", NS):
        nums = [float(v) for v in p.get("d").removeprefix("M").split()]
        yield from zip(nums[::2], nums[1::2], strict=True)


def test_no_label_goes_past_the_edge_of_the_map():
    frame = fit(TL, BR, "A4", orientation="landscape")
    (top, left), (bottom, right) = frame.corners()
    cy, cx = (top + bottom) / 2, (left + right) / 2
    tiny = (right - left) / 1000
    feats = {
        # A road from the top edge to the middle: its name must stop short of the frame.
        "street-names": [
            Item("major", LineString([(cx, top - tiny), (cx + 3 * tiny, cy)]), "Rúa"),
            # One all along the edge: no room for its name at all.
            Item("major", LineString([(left, top - tiny), (right, top - tiny)]), "Borde"),
        ],
        "places": [
            Item("village", Point(left + tiny, cy), "Sarela de Abaixo"),  # point in, text out
            Item("town", Point(cx, cy), "Compostela"),
        ],
    }
    job = Job("a", frame, load("poster"), select(["street-names", "places"]), feats)
    root = ET.fromstring(render([job]))
    assert root.find(".//svg:g[@id='a-places-village']", NS) is None
    assert [t.text for t in root.findall(".//svg:g[@id='a-places-town']/svg:text", NS)] == [
        "Compostela"
    ]
    style = job.theme.style("street-names", "major")
    room = style["font-size"] / 2 + style["stroke-width"] / 2
    ys = [y for _, y in _defs_xy(root)]
    assert ys  # the name is still written, on the part of the road away from the edge
    assert min(ys) >= frame.map_y + room - 0.01


def test_in_a_circle_a_name_in_the_corner_is_left_out():
    frame = fit(TL, BR, "A4", orientation="landscape", shape="circle")
    (top, left), _ = frame.corners()
    feats = {"places": [Item("village", Point(left + 0.0002, top - 0.0002), "Canto")]}
    job = Job("a", frame, load("color"), select(["places"]), feats)
    root = ET.fromstring(render([job]))
    assert root.find(".//svg:g[@id='a-places-village']", NS) is None


def test_a_pattern_fill_points_at_a_pattern_of_its_zone():
    feats = {
        "buildings": [Item("building", square(-8.545, 42.881, 0.001))],
        "green": [Item("green", square(-8.544, 42.880, 0.001))],
    }
    frame = fit(TL, BR, "A4", orientation="landscape")
    job = Job("b", frame, load("vintage"), select(["green", "buildings"]), feats)
    root = ET.fromstring(render([job]))
    building = root.find(".//svg:path[@id='b-buildings-building']", NS)
    assert building.get("fill") == "url(#b-pattern-houses)"
    houses = root.find(".//svg:pattern[@id='b-pattern-houses']", NS)
    assert houses.get("patternUnits") == "userSpaceOnUse"
    assert houses.get("patternTransform") == "rotate(45)"
    assert houses.find("svg:line", NS) is not None and houses.find("svg:rect", NS) is not None
    meadow = root.find(".//svg:pattern[@id='b-pattern-meadow']", NS)
    # Staggered crosses: a tile two rows high, one cross in the middle of the first and
    # one cut in half at each side of the second.
    assert (meadow.get("width"), meadow.get("height")) == ("2", "4")
    assert meadow.find("svg:path", NS).get("d").count("M") == 6  # two strokes per cross
    # Only the patterns the zone's layers use: no water layer here, no water pattern.
    assert root.find(".//svg:pattern[@id='b-pattern-water']", NS) is None


def test_a_margin_colour_paints_the_sheet_and_leaves_the_background_to_the_map():
    frame = fit(TL, BR, "A4", orientation="landscape")
    job = Job("a", frame, load("vintage"), select(["roads"]), {"roads": []})
    page = ET.fromstring(render([job])).find(".//svg:g[@id='page']", NS)
    sheet, inner = page
    assert sheet.get("fill") == "#ffffff" and sheet.get("width") == _num(frame.page_w)
    assert inner.get("fill") == "#f4ecd2"
    assert (inner.get("x"), inner.get("width")) == (_num(frame.map_x), _num(frame.map_w))
    # Without a margin colour, one sheet in the background, as before.
    plain = Job("a", frame, load("bw"), select(["roads"]), {"roads": []})
    assert len(ET.fromstring(render([plain])).find(".//svg:g[@id='page']", NS)) == 1


def _arrow(svg):
    north = ET.fromstring(svg).find(".//svg:g[@id='north']", NS)
    (turned,) = north
    return turned


def test_every_map_has_a_north_arrow_in_its_top_right_corner():
    job = make_job("a", TL, BR, "dark")
    f = job.frame
    turned = _arrow(render([job]))
    assert turned.find("svg:text", NS).text == "N"
    x, y = map(float, turned.get("transform").split(")")[0].removeprefix("translate(").split())
    assert f.map_x + f.map_w * 0.9 < x < f.map_x + f.map_w
    assert f.map_y < y < f.map_y + f.map_h * 0.1
    # In the theme's colours: ink, and a halo of the page.
    page = job.theme.page
    assert {p.get("fill") for p in turned.findall("svg:path", NS)} >= {page["ink"]}
    assert turned.find("svg:path", NS).get("stroke") == page["background"]


@pytest.mark.parametrize("lon, sign", [(-8.55, -1), (-9.0, 0), (-9.45, 1)])
def test_the_arrow_points_to_true_north_not_the_grid(lon, sign):
    # UTM zone 29 has its central meridian at 9 W: east of it, true north leans to
    # the left of the grid's (and to the right west of it); on it, they are the same.
    frame = fit((42.884, lon - 0.006), (42.878, lon + 0.006), "A4")
    angle = true_north(frame)
    assert abs(angle) < 1
    assert (round(angle, 2) > 0) - (round(angle, 2) < 0) == sign


def _water_job(theme, feats):
    frame = fit(TL, BR, "A4", orientation="landscape")
    return Job("a", frame, load(theme), select(["water"]), feats)


def _area(root, path_id):
    """Area in mm² of a path's rings (even-odd, as drawn)."""
    path = root.find(f".//svg:path[@id='{path_id}']", NS)
    if path is None:
        return 0.0
    total = 0.0
    for ring in path.get("d").removeprefix("M").split("M"):
        nums = [float(v) for v in ring.rstrip("Z").split()]
        total += Polygon(list(zip(nums[::2], nums[1::2], strict=True))).area
    return total


def test_joined_rivers_flow_into_the_lake_as_one_body_and_streams_stop_at_its_edge():
    lake = square(-8.546, 42.880, 0.002)
    river = LineString([(-8.550, 42.881), (-8.540, 42.881)])  # in, through the lake and out
    stream = LineString([(-8.550, 42.8815), (-8.540, 42.8815)])
    feats = {"water": [Item("water", lake), Item("river", river), Item("stream", stream)]}
    alone = ET.fromstring(render([_water_job("vintage-bw", {"water": [Item("water", lake)]})]))
    alone = _area(alone, "a-water-water")
    root = ET.fromstring(render([_water_job("vintage-bw", feats)]))
    # The river is gone as a line: it is part of the water, which grew by its banks.
    assert root.find(".//svg:path[@id='a-water-river']", NS) is None
    assert _area(root, "a-water-water") > alone + 10
    # The stream is cut out of the body: two stretches, none inside it.
    stream = root.find(".//svg:path[@id='a-water-stream']", NS).get("d")
    assert stream.count("M") == 2


def test_shore_lines_follow_the_shore_but_not_the_edge_of_the_map():
    lake = square(-8.546, 42.880, 0.002)
    root = ET.fromstring(render([_water_job("vintage", {"water": [Item("water", lake)]})]))
    shore = root.find(".//svg:path[@id='a-water-water-shore']", NS)
    assert shore.get("stroke-width") == "0.08" and shore.get("shore-lines") is None
    assert root.find(".//svg:path[@id='a-water-water']", NS).get("join") is None
    assert shore.get("d").count("M") == 4  # one ring per distance
    # Water past every edge of the map: it has no shore on the paper.
    sea = square(-8.56, 42.87, 0.03)
    root = ET.fromstring(render([_water_job("vintage", {"water": [Item("water", sea)]})]))
    assert root.find(".//svg:path[@id='a-water-water']", NS) is not None
    assert root.find(".//svg:path[@id='a-water-water-shore']", NS) is None


def _title(root):
    return root.find(".//svg:g[@id='title']/svg:text", NS)


def _mark(root):
    return root.find(".//svg:g[@id='legend']/svg:text[@text-anchor='end']", NS)


@pytest.mark.parametrize("shape", ["rect", "circle"])
@pytest.mark.parametrize("legend", ["full", "minimal"])
def test_the_title_sits_under_the_mark_and_nothing_else_is_on_top(shape, legend):
    frame = fit(TL, BR, "A5", shape=shape, titled=True)
    job = Job("a", frame, load("vintage"), select(["roads"]), {})
    root = ET.fromstring(render([job], legend, title="Santiago de Compostela"))
    t = _title(root)
    size, y = float(t.get("font-size")), float(t.get("y"))
    assert t.text == "Santiago de Compostela"
    assert (t.get("text-anchor"), float(t.get("x"))) == ("middle", pytest.approx(frame.page_w / 2))
    assert y - CAP_HEIGHT * size > 0 and y < frame.map_y  # over the map, on the paper
    # the mark keeps its place top right, centred in the margin, well over the capitals
    mark = _mark(root)
    mark_size = float(mark.get("font-size"))
    assert float(mark.get("y")) == pytest.approx(frame.margin / 2 + 0.35 * mark_size, abs=0.01)
    assert float(mark.get("y")) + 0.25 * mark_size < y - CAP_HEIGHT * size
    # the rest of the legend is under the map
    for other in root.findall(".//svg:g[@id='legend']/svg:text", NS):
        assert other is mark or float(other.get("y")) > frame.map_y + frame.map_h
    # in the theme's lettering and ink
    assert "Garamond" in t.get("font-family") and t.get("font-style") == "italic"
    assert t.get("fill") == job.theme.page["ink"]
    assert root.find("svg:title", NS).text.startswith("Santiago de Compostela — ")


def test_a_circle_with_a_title_is_centred_under_the_band():
    frame = fit(TL, BR, "A4", shape="circle", titled=True)
    root = ET.fromstring(render([Job("a", frame, load("bw"), [], {})], title="X"))
    for circle in (
        root.find(".//svg:clipPath[@id='clip-a']/svg:circle", NS),
        root.find(".//svg:g[@id='frame']/svg:circle", NS),
    ):
        assert float(circle.get("cy")) == pytest.approx(frame.map_cy, abs=0.01)
        assert float(circle.get("cy")) > frame.page_h / 2


def test_a_long_title_shrinks_to_the_width_of_the_map():
    frame = fit(TL, BR, "A5", titled=True)
    title = "A very long title for such a small sheet of paper, it goes on and on"
    t = _title(ET.fromstring(render([Job("a", frame, load("bw"), [], {})], title=title)))
    # within the rounding of the size to hundredths of a mm
    assert len(title) * float(t.get("font-size")) * CHAR_WIDTH <= frame.print_w * 1.005


def test_no_title_no_band_no_layer():
    root = ET.fromstring(render([make_job("a", TL, BR, "bw")], title="Ignored"))
    assert _title(root) is None  # the frame left no band for it
    assert root.find(".//svg:g[@id='title']", NS) is None


@pytest.mark.parametrize("paper", ["A5", "A4", "A0"])
@pytest.mark.parametrize("legend", ["full", "minimal"])
@pytest.mark.parametrize("shape", ["rect", "circle"])
def test_the_title_row_is_centred_between_the_top_of_the_paper_and_the_band(paper, legend, shape):
    frame = fit(TL, BR, paper, margin=6, shape=shape, orientation="portrait", titled=True)
    root = ET.fromstring(render([Job("a", frame, load("vintage"), [], {})], legend, title="Ab"))
    t = _title(root)
    size, baseline = float(t.get("font-size")), float(t.get("y"))
    above = baseline - CAP_HEIGHT * size  # the paper's edge to the capitals
    below = frame.margin + frame.title_band - baseline  # the baseline to the band's bottom
    assert above > 0 and above == pytest.approx(below, abs=0.02)
    assert frame.margin + frame.title_band <= frame.map_y + 1e-9


def test_without_a_title_the_mark_is_in_the_middle_of_the_top_margin():
    job = make_job("a", TL, BR, "bw")
    mark = _mark(ET.fromstring(render([job])))
    size = float(mark.get("font-size"))
    assert float(mark.get("y")) == pytest.approx(job.frame.margin / 2 + 0.35 * size, abs=0.01)

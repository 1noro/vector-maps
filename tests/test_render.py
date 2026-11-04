import xml.etree.ElementTree as ET

import pytest
from shapely.geometry import LineString, Point, Polygon

from vectormaps.area import fit
from vectormaps.labels import CHAR_WIDTH
from vectormaps.layers import select
from vectormaps.pipeline import Item
from vectormaps.render import MARK, Job, _corner, legend_lines, path_data, render
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
    assert ids == ["page", "area-a", "area-b", "frame", "legend"]  # b is drawn over a
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
    assert root.find(".//svg:path", NS) is None


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
    assert texts[0].startswith("© OpenStreetMap contributors (ODbL)")
    assert f"1:{job.frame.scale}" in texts[0]
    tl, br = job.frame.corners()
    assert texts[1] == f"↖ {tl[0]:.5f}, {tl[1]:.5f} · ↘ {br[0]:.5f}, {br[1]:.5f}"
    assert texts[2] == "Generated with vector-maps by 1noro"
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
    corners = legend_lines([a, b])[1]
    assert corners.startswith("A: ↖ ") and "   |   B: ↖ " in corners


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
def test_rect_and_square_have_no_clip_and_a_rect_outline(shape):
    root = ET.fromstring(render([_shaped_job(shape)]))
    assert root.find(".//svg:clipPath", NS) is None
    outline = root.find(".//svg:g[@id='frame']/svg:rect", NS)
    w = float(outline.get("width"))
    assert w == pytest.approx(277 if shape == "rect" else 190)


def test_circle_legend_gives_the_centre_instead_of_the_corners():
    job = _shaped_job("circle")
    lat, lon = job.frame.center()
    assert lat == pytest.approx((TL[0] + BR[0]) / 2, abs=1e-4)
    assert lon == pytest.approx((TL[1] + BR[1]) / 2, abs=1e-4)
    full = legend_lines([job])
    assert full[1] == f"⌖ {lat:.5f}, {lon:.5f}"
    assert "↖" not in "".join(full) and "↘" not in "".join(full)
    assert legend_lines([job], "minimal")[0].startswith(f"⌖ {lat:.5f}, {lon:.5f} · 1:")
    square = legend_lines([_shaped_job("square")])
    assert "↖" in square[1]  # only the circle changes


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
        assert "↖" in lines[1] and "°" in lines[1] and "." in lines[1]
        assert "°" in legend_lines([job], "minimal", coords)[0]
        assert "°" in render([job], "full", coords)
    assert "°" not in legend_lines([job])[1]  # decimal degrees by default
    with pytest.raises(ValueError, match="coordinate format"):
        legend_lines([job], "full", "utm")
    circle = legend_lines([_shaped_job("circle")], "full", "dms")
    assert circle[1].startswith("⌖ 42°") and "N" in circle[1]


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


def test_no_casing_where_the_theme_has_none():
    root = ET.fromstring(render([make_job("a", TL, BR, "bw")]))
    assert root.find(".//svg:path[@id='a-roads-minor-casing']", NS) is None

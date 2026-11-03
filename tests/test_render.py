import xml.etree.ElementTree as ET

import pytest
from shapely.geometry import LineString, Polygon

from vectormaps.area import fit
from vectormaps.layers import select
from vectormaps.render import Job, path_data, render
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
        "buildings": [("building", square(cx - 0.0005, cy - 0.0005, 0.001))],
        # Longer than the page, so it has to be clipped.
        "roads": [("minor", LineString([(tl[1] - 0.01, cy), (br[1] + 0.01, cy)]))],
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
    assert ids == ["page", "area-a", "area-b", "frame"]  # b is drawn over a
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

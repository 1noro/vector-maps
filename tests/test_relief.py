import io
import subprocess
import urllib.error
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from vectormaps import relief
from vectormaps.area import fit
from vectormaps.layers import select
from vectormaps.pipeline import load_features
from vectormaps.render import Job, render
from vectormaps.theme import load

# Roughly 1.0 km wide and 0.8 km high, in Santiago de Compostela: tile N42 W009.
TL = (42.8845, -8.5510)
BR = (42.8775, -8.5385)
TILE = "Copernicus_DSM_COG_10_N42_00_W009_00_DEM"


def test_tile_names_follow_the_south_west_corner():
    assert relief.tile_name(42, -9) == TILE
    assert relief.tile_name(-1, 0) == "Copernicus_DSM_COG_10_S01_00_E000_00_DEM"
    # Santiago, and an area across the 43rd parallel and the 8th meridian.
    assert relief.tiles_for((42.87, -8.56, 42.89, -8.53)) == [TILE]
    assert len(relief.tiles_for((42.9, -8.1, 43.1, -7.9))) == 4


def test_contour_step_follows_the_scale():
    assert relief.contour_step(fit(TL, BR, "A4")) == 5  # 1:4120, a town plan
    assert relief.contour_step(fit((43.5, -9.2), (42.0, -7.0), "A4")) == 500


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def test_a_tile_is_downloaded_once(tmp_path, monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        return FakeResponse(b"II*\x00tiff")

    monkeypatch.setattr(relief.urllib.request, "urlopen", fake_urlopen)
    first = relief.fetch_tile(TILE, tmp_path)
    assert relief.fetch_tile(TILE, tmp_path) == first
    assert first.read_bytes() == b"II*\x00tiff"
    assert len(calls) == 1 and calls[0].endswith(f"{TILE}/{TILE}.tif")
    assert not list(tmp_path.glob("*.part"))


def test_no_tile_means_sea_and_is_not_asked_again(tmp_path, monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req)
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(relief.urllib.request, "urlopen", fake_urlopen)
    assert relief.fetch_tile(TILE, tmp_path) is None
    assert relief.fetch_tile(TILE, tmp_path) is None
    assert len(calls) == 1


def test_a_failed_download_leaves_nothing(tmp_path, monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 500, "boom", {}, None)

    monkeypatch.setattr(relief.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(relief.ReliefError, match="HTTP 500"):
        relief.fetch_tile(TILE, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def hill_cache(tmp_path):
    """A cache holding a hand-made tile N42 W009: a 300 m hill over Santiago."""
    n = 361
    lon = np.linspace(-9, -8, n)
    lat = np.linspace(43, 42, n)
    x, y = np.meshgrid(lon, lat)
    z = 300 * np.exp(-(((x + 8.545) ** 2 + (y - 42.881) ** 2) / (2 * 0.01**2)))
    asc = tmp_path / "hill.asc"
    header = f"ncols {n}\nnrows {n}\nxllcorner -9.0\nyllcorner 42.0\ncellsize {1 / (n - 1)}\n"
    asc.write_text(header + "\n".join(" ".join(f"{v:.2f}" for v in row) for row in z))
    dem = tmp_path / "cache" / "dem"
    dem.mkdir(parents=True)
    subprocess.run(
        ["gdal_translate", "-q", "-a_srs", "EPSG:4326", asc, dem / f"{TILE}.tif"],
        check=True,
        capture_output=True,
    )
    return tmp_path / "cache"


def test_contours_and_hillshade_from_the_dem(hill_cache):
    frame = fit(TL, BR, "A4")
    feats = load_features(frame, select(["hillshade", "contours"]), source=None, cache=hill_cache)
    lines = feats["contours"]
    assert {item.cls for item in lines} == {"minor", "major"}
    south, west, north, east = frame.lonlat_bounds()
    for item in lines:
        x0, y0, x1, y1 = item.geom.bounds
        assert west <= x0 and x1 <= east and south <= y0 and y1 <= north
    (shade,) = feats["hillshade"]
    assert shade.raster.exists()

    svg = render([Job("a", frame, load("bw"), select(["hillshade", "contours"]), feats)])
    assert 'xlink:href="data:image/png;base64,iVBORw0KGgo' in svg  # a PNG
    assert 'id="a-contours-major"' in svg
    # Its licence asks for this notice, word for word, on anything derived from it.
    assert "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014" in svg
    assert "provided under COPERNICUS by the European Union and ESA; all rights reserved" in svg


def test_no_relief_no_copernicus_credit(hill_cache):
    frame = fit(TL, BR, "A4")
    svg = render([Job("a", frame, load("bw"), select(["roads"]), {"roads": []})])
    assert "Copernicus" not in svg


def test_open_sea_has_no_relief(tmp_path, monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(relief.urllib.request, "urlopen", fake_urlopen)
    frame = fit((42.5, -15.1), (42.49, -15.08), "A5")  # the Atlantic
    feats = load_features(frame, select(["contours"]), source=None, cache=tmp_path)
    assert feats["contours"] == []


def _row_through_the_hill(dem, tmp_path):
    asc = tmp_path / "frame.asc"
    subprocess.run(["gdal_translate", "-q", "-of", "AAIGrid", dem, asc], check=True)
    lines = asc.read_text().splitlines()
    rows = [list(map(float, ln.split())) for ln in lines if ln and not ln[0].isalpha()]
    z = np.array(rows)
    return z[np.unravel_index(z.argmax(), z.shape)[0]]


@pytest.mark.parametrize("method, smooth", [("bilinear", False), ("cubicspline", True)])
def test_zoomed_in_the_ground_is_smooth_not_a_plane_per_cell(
    hill_cache, tmp_path, monkeypatch, method, smooth
):
    # A frame much finer than the tile's cells (~300 m here, 30 m in Copernicus).
    monkeypatch.setattr(relief, "RESAMPLING", method)
    frame = fit(TL, BR, "A4")
    row = _row_through_the_hill(relief.frame_dem(frame, hill_cache / "dem"), tmp_path)
    bends = np.abs(np.diff(row, 2))
    # A plane per cell: the slope only changes at the cell edges, flat in between.
    flat = np.mean(bends < bends.max() * 0.01)
    assert (flat < 0.5) == smooth


def _notice(svg):
    root = ET.fromstring(svg)
    ns = {"svg": "http://www.w3.org/2000/svg"}
    for t in root.findall(".//svg:g[@id='legend']/svg:text", ns):
        if t.text and t.text.startswith("Relief produced"):
            return t
    raise AssertionError("no relief notice")


@pytest.mark.parametrize("legend", ["full", "minimal"])
def test_the_relief_notice_is_a_second_line_at_the_bottom_like_the_first(hill_cache, legend):
    frame = fit(TL, BR, "A4")
    layers = select(["hillshade", "contours"])
    feats = load_features(frame, layers, source=None, cache=hill_cache)
    svg = render([Job("a", frame, load("bw"), layers, feats)], legend)
    notice = _notice(svg)
    ns = {"svg": "http://www.w3.org/2000/svg"}
    first = ET.fromstring(svg).find(".//svg:g[@id='legend']/svg:text", ns)
    assert notice.text == relief.ATTRIBUTION  # whole: its licence has no short form
    assert float(first.get("y")) < float(notice.get("y")) < frame.page_h
    assert float(first.get("y")) > frame.map_y + frame.map_h  # both under the map
    assert first.get("x") == notice.get("x")
    for attr in ("font-family", "font-size", "fill", "fill-opacity"):
        assert notice.get(attr) == first.get(attr)


def test_without_relief_there_is_no_notice(hill_cache):
    frame = fit(TL, BR, "A4")
    svg = render([Job("a", frame, load("bw"), select(["roads"]), {})], "full")
    assert "Relief produced" not in svg


def test_a_hatch_only_draws_where_the_grid_is_above_its_threshold():
    grid = np.zeros((10, 20))
    grid[:, 10:] = 30  # steep on the right half of the box only
    d = relief.hatch(grid, (100.0, 50.0, 40.0, 20.0), above=10, spacing=1, angle=90)
    xs = [float(seg.split()[0]) for seg in d.split("M")[1:]]
    assert len(xs) > 10
    assert all(120 <= x <= 140 for x in xs)  # vertical lines, all in the right half
    assert relief.hatch(grid, (100.0, 50.0, 40.0, 20.0), 40, 1, 90) == ""


def _length(d):
    total = 0.0
    for seg in d.split("M")[1:]:
        a, b = seg.split("L")
        (x0, y0), (x1, y1) = map(float, a.split()), map(float, b.split())
        total += np.hypot(x1 - x0, y1 - y0)
    return total


def _band_lengths(svg):
    root = ET.fromstring(svg)
    paths = root.iter("{http://www.w3.org/2000/svg}path")
    return {p.get("id"): _length(p.get("d")) for p in paths if "-band-" in p.get("id", "")}


def test_a_hatched_hillshade_is_lines_steeper_bands_drawing_less(hill_cache, tmp_path):
    theme = tmp_path / "hatched.toml"
    theme.write_text(
        '[page]\nbackground = "#ffffff"\nink = "#000000"\nframe-width = 0.3\n'
        '[layers.hillshade.shade]\nstyle = "hatch"\nbands = [\n'
        '  { slope = 2, spacing = 1, angle = 30, color = "#c8643c" },\n'
        "  { slope = 8, spacing = 1, angle = -30 },\n"
        "]\n"
    )
    frame = fit(TL, BR, "A4")
    layers = select(["hillshade"])
    feats = load_features(frame, layers, source=None, cache=hill_cache)
    svg = render([Job("a", frame, load(str(theme)), layers, feats)])
    assert "data:image/png" not in svg  # no picture
    lines = _band_lengths(svg)
    assert set(lines) == {"a-hillshade-band-1", "a-hillshade-band-2"}
    assert 0 < lines["a-hillshade-band-2"] < lines["a-hillshade-band-1"]
    assert "Relief produced using Copernicus" in svg  # still derived from the DEM

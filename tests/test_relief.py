import io
import subprocess
import urllib.error

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
    assert "Copernicus DEM GLO-30" in svg  # its licence asks for the credit


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

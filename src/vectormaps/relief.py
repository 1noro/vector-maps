"""Relief from an elevation model: contour lines and hillshade (ADR 0008).

OSM has no terrain, so the elevations come from the Copernicus DEM GLO-30 (30 m,
the whole planet), open on AWS with no account or key. Its 1x1 degree tiles are
downloaded once into the cache; GDAL does the rest (gdalwarp, gdal_contour,
gdaldem) in the map's own UTM grid, so the hillshade lines up with the page.
"""

import hashlib
import http.client
import json
import logging
import math
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import shape

from vectormaps.area import Frame
from vectormaps.download import USER_AGENT
from vectormaps.overpass import RETRY_STATUS, retry_after
from vectormaps.tmpfile import tmp_beside

log = logging.getLogger(__name__)

TILE_URL = "https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif"
ATTRIBUTION = (
    "Relief: Copernicus DEM GLO-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space "
    "GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved"
)
MAX_ATTEMPTS = 3
CELL_MM = 0.25  # one DEM cell on paper (~100 dpi): fine for print, light enough for A0
# A smooth surface between the 30 m cells (Nov 4). Bilinear gave a plane per cell, so a
# zoomed-in hillshade (one shade per slope) came out in squares of 30 m.
RESAMPLING = "cubicspline"
STEPS = (5, 10, 20, 25, 50, 100, 200, 250, 500)  # m; under 5 m the 30 m DEM is noise
MAJOR_EVERY = 5  # every 5th contour is a major (index) one
FLAT = 180  # gdaldem's shade of flat ground with the sun at 45 degrees: shown transparent
# Most ground is gentle: in Santiago 90% of the shade falls within 136-212. So the
# shadow is full 80 below flat and the light 50 above, not at the ends (0, 255).
SHADOW_RANGE = 80
LIGHT_RANGE = 50
HIGHLIGHT_ALPHA = 140  # how much the slopes facing the sun light up, 0-255
GDAL_ENV = {**os.environ, "GDAL_PAM_ENABLED": "NO"}  # no .aux.xml files next to the outputs


class ReliefError(RuntimeError):
    pass


def tile_name(lat: int, lon: int) -> str:
    """The Copernicus tile whose south-west corner is (lat, lon)."""
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


def tiles_for(bounds: tuple[float, float, float, float]) -> list[str]:
    s, w, n, e = bounds
    lats = range(math.floor(s), math.ceil(n))
    lons = range(math.floor(w), math.ceil(e))
    return [tile_name(lat, lon) for lat in lats for lon in lons]


def fetch_tile(name: str, cache_dir: Path, sleep=time.sleep) -> Path | None:
    """The tile, downloaded once (~40 MB); None where there is none (open sea)."""
    path = cache_dir / f"{name}.tif"
    sea = cache_dir / f"{name}.none"
    if path.exists():
        return path
    if sea.exists():
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(TILE_URL.format(name=name), headers={"User-Agent": USER_AGENT})
    tmp = tmp_beside(path)
    log.info("downloading elevation tile %s (~40 MB, once)", name)
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp, tmp.open("wb") as fh:
                    shutil.copyfileobj(resp, fh, 1 << 20)
                break
            except urllib.error.HTTPError as err:
                if err.code == 404:
                    sea.touch()  # no tile: all sea there
                    return None
                if err.code not in RETRY_STATUS or attempt == MAX_ATTEMPTS:
                    raise ReliefError(f"elevation tile {name}: HTTP {err.code}") from err
                header = err.headers.get("Retry-After") if err.headers else None
                wait = retry_after(header, 30 * attempt)
                log.warning(
                    "elevation server answered HTTP %d; attempt %d/%d in %d s",
                    err.code,
                    attempt + 1,
                    MAX_ATTEMPTS,
                    wait,
                )
                sleep(wait)
            except urllib.error.URLError as err:
                raise ReliefError(f"cannot reach the elevation server: {err.reason}") from err
            except (TimeoutError, http.client.HTTPException, ConnectionError) as err:
                raise ReliefError(f"elevation tile {name} cut short; try again") from err
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def _gdal(cmd: list[str]) -> None:
    done = subprocess.run(cmd, capture_output=True, text=True, env=GDAL_ENV)
    if done.returncode != 0:
        raise ReliefError(f"{cmd[0]} failed: {done.stderr.strip()[-500:]}")


def frame_dem(frame: Frame, cache_dir: Path) -> Path | None:
    """Elevations over the map, on a grid aligned with it (a cell is CELL_MM on paper).

    None if the whole area is open sea. Cached by frame.
    """
    tiles = [t for n in tiles_for(frame.lonlat_bounds()) if (t := fetch_tile(n, cache_dir))]
    if not tiles:
        return None
    cols = max(2, round(frame.map_w / CELL_MM))
    rows = max(2, round(frame.map_h / CELL_MM))
    epsg = f"EPSG:{frame.crs.to_epsg()}"
    box = [frame.xmin, frame.ymin, frame.xmax, frame.ymax]
    raw = f"{epsg}|{box}|{cols}x{rows}|{[t.name for t in tiles]}|{RESAMPLING}"
    out = cache_dir / f"frame-{hashlib.sha1(raw.encode()).hexdigest()[:16]}.tif"
    if not out.exists():
        tmp = tmp_beside(out)
        try:
            _gdal(
                ["gdalwarp", "-q", "-overwrite", "-t_srs", epsg, "-r", RESAMPLING]
                + ["-te", *(f"{v:.3f}" for v in box), "-ts", str(cols), str(rows)]
                + ["-wo", "INIT_DEST=0", "-ot", "Float32"]  # missing tiles are sea: 0 m
                + [str(t) for t in tiles]
                + [str(tmp)]
            )
            tmp.replace(out)
        finally:
            tmp.unlink(missing_ok=True)
    return out


def contour_step(frame: Frame) -> int:
    """Metres between contour lines, from the scale: 5 m in a town plan, 10 m at 1:25000."""
    target = frame.scale / 2500
    return next((s for s in STEPS if s >= target), STEPS[-1])


def contours(frame: Frame, dem: Path) -> list[tuple[str, float, shapely.Geometry]]:
    """(class, elevation, line in lon/lat) for every contour above sea level."""
    step = contour_step(frame)
    out_path = dem.with_name(f"{dem.stem}-contours-{step}.geojson")
    if not out_path.exists():
        tmp = tmp_beside(out_path)  # fresh: gdal_contour does not overwrite
        try:
            _gdal(
                ["gdal_contour", "-q", "-a", "ELEV", "-i", str(step), "-f", "GeoJSON"]
                + [str(dem), str(tmp)]
            )
            tmp.replace(out_path)
        finally:
            tmp.unlink(missing_ok=True)
    back = Transformer.from_crs(frame.crs, 4326, always_xy=True)

    def to_lonlat(coords: np.ndarray) -> np.ndarray:
        x, y = back.transform(coords[:, 0], coords[:, 1])
        return np.column_stack((x, y))

    tolerance = frame.metres_per_mm * 0.1  # 0.1 mm on paper
    items = []
    for feat in json.loads(out_path.read_text(encoding="utf-8")).get("features", []):
        elev = float(feat["properties"]["ELEV"])
        if elev <= 0 or not feat.get("geometry"):
            continue
        line = shape(feat["geometry"]).simplify(tolerance)
        cls = "major" if round(elev) % (step * MAJOR_EVERY) == 0 else "minor"
        items.append((cls, elev, shapely.transform(line, to_lonlat)))
    return items


def hillshade(dem: Path) -> Path:
    """Shade of the ground, 0 (dark) to 255 (lit), sun from the north-west at 45 degrees."""
    out = dem.with_name(f"{dem.stem}-shade.tif")
    if not out.exists():
        tmp = tmp_beside(out)
        try:
            _gdal(["gdaldem", "hillshade", "-q", "-compute_edges", str(dem), str(tmp)])
            tmp.replace(out)
        finally:
            tmp.unlink(missing_ok=True)
    return out


def _rgb(hex_colour: str) -> str:
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return " ".join(str(int(h[i : i + 2], 16)) for i in (0, 2, 4))


def shade_png(shade: Path, shadow: str, highlight: str) -> bytes:
    """The hillshade as a transparent PNG: flat ground clear, slopes in the theme's colours."""
    table = tmp_beside(shade.with_name(shade.stem + ".colours.txt"))
    png = tmp_beside(shade.with_name(shade.stem + ".png"))
    dark, light = _rgb(shadow), _rgb(highlight)
    # Shade value -> colour and alpha, linear in between; "nv" is gdaldem's no-data.
    table.write_text(
        "nv 0 0 0 0\n"
        f"0 {dark} 255\n"
        f"{FLAT - SHADOW_RANGE} {dark} 255\n"
        f"{FLAT} {dark} 0\n"
        f"{FLAT + 1} {light} 0\n"
        f"{FLAT + LIGHT_RANGE} {light} {HIGHLIGHT_ALPHA}\n"
        f"255 {light} {HIGHLIGHT_ALPHA}\n"
    )
    try:
        _gdal(
            ["gdaldem", "color-relief", "-q", "-alpha", "-of", "PNG", str(shade), str(table)]
            + [str(png)]
        )
        return png.read_bytes()
    finally:
        table.unlink(missing_ok=True)
        png.unlink(missing_ok=True)

"""Where the OSM data comes from: the Overpass API or a local PBF extract (ADR 0002).

Both give the same thing, features in lon/lat as (kind, tags, geometry), so the
rest of the program does not care which one was used.
"""

import hashlib
import logging
import re
import subprocess
from pathlib import Path
from typing import Protocol

from shapely.geometry.base import BaseGeometry

from vectormaps import osmexport, overpass
from vectormaps.layers import Layer
from vectormaps.tmpfile import tmp_beside

log = logging.getLogger(__name__)

Bounds = tuple[float, float, float, float]  # south, west, north, east
Feature = tuple[str, dict[str, str], BaseGeometry]


def header_box(pbf: Path) -> tuple[float, float, float, float] | None:
    """(west, south, east, north) from the PBF header (Geofabrik and osmium write one)."""
    done = subprocess.run(
        ["osmium", "fileinfo", "-g", "header.boxes", str(pbf)],
        capture_output=True,
        text=True,
    )
    nums = re.findall(r"-?\d+(?:\.\d+)?", done.stdout) if done.returncode == 0 else []
    if len(nums) < 4:
        return None
    w, s, e, n = (float(v) for v in nums[:4])
    return w, s, e, n


def local_pbf_for(areas: list[Bounds], pbf_dir: Path) -> Path | None:
    """The smallest .osm.pbf in `pbf_dir` whose header box holds every one of the areas."""
    best: tuple[float, Path] | None = None
    for pbf in sorted(pbf_dir.glob("*.osm.pbf")):
        cover = header_box(pbf)
        if cover is None:
            continue
        cw, cs, ce, cn = cover
        if all(cw <= w and cs <= s and ce >= e and cn >= n for s, w, n, e in areas):
            size = (ce - cw) * (cn - cs)
            if best is None or size < best[0]:
                best = size, pbf
    return best[1] if best else None


class Source(Protocol):
    name: str  # what the log says the data comes from

    def check(self, bounds: Bounds) -> None:
        """Raise ValueError if this source cannot have data for the area."""
        ...

    def features(self, layer: Layer, bounds: Bounds) -> list[Feature]: ...


class OverpassSource:
    """One query per layer and area, cached on disk by the exact query."""

    name = "Overpass"

    def __init__(self, cache_dir: Path, url: str | None = None):
        self.cache_dir = cache_dir / "overpass"
        self.url = url

    def check(self, bounds: Bounds) -> None:
        pass  # Overpass covers the planet

    def features(self, layer: Layer, bounds: Bounds) -> list[Feature]:
        osm = overpass.fetch(layer.overpass_query(bounds), self.cache_dir, self.url)
        geojson = osmexport.export(osm, osmexport.exported_name(osm))
        return list(osmexport.read_features(geojson))


class PbfSource:
    """A local extract (e.g. from Geofabrik), cut once per area with osmium.

    The cut uses the `smart` strategy so multipolygons that cross the edge of
    the area (a big park, a lake) keep all their members and come out whole.
    """

    def __init__(self, pbf: Path, cache_dir: Path):
        if not pbf.is_file():
            raise ValueError(f"PBF file not found: {pbf} (see `make pbf`)")
        self.pbf = pbf
        self.name = f"local extract {pbf.name}"
        self.cache_dir = cache_dir / "pbf"
        self._memo: dict[Bounds, list[Feature]] = {}
        self.coverage = header_box(pbf)  # (west, south, east, north), if the file says

    def check(self, bounds: Bounds) -> None:
        if self.coverage is None:
            return  # no box in the header: the pipeline warns if nothing comes out
        s, w, n, e = bounds
        cw, cs, ce, cn = self.coverage
        inside = max(0.0, min(e, ce) - max(w, cw)) * max(0.0, min(n, cn) - max(s, cs))
        share = inside / ((e - w) * (n - s))
        if share == 0:
            raise ValueError(
                f"the area is outside {self.pbf.name}, which covers latitudes {cs:.2f} to "
                f"{cn:.2f} and longitudes {cw:.2f} to {ce:.2f}. Download an extract that "
                "includes it: make pbf URL=<…-latest.osm.pbf> (list: https://download.geofabrik.de/)"
            )
        if share < 0.98:
            log.warning(
                "only %.0f%% of the area is inside %s; the rest will be empty",
                share * 100,
                self.pbf.name,
            )

    def _key(self, bounds: Bounds) -> str:
        stat = self.pbf.stat()
        raw = f"{self.pbf.resolve()}|{stat.st_mtime_ns}|{stat.st_size}|{bounds}|{osmexport.VERSION}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    def _all(self, bounds: Bounds) -> list[Feature]:
        if bounds not in self._memo:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            key = self._key(bounds)
            extract = tmp_beside(self.cache_dir / f"{key}.osm.pbf")  # dropped once exported
            geojson = self.cache_dir / f"{key}.geojsonseq"
            if not geojson.exists():
                s, w, n, e = bounds
                log.info("cutting %s with osmium", self.pbf.name)
                cmd = [
                    "osmium", "extract", "--overwrite", "--strategy=smart",
                    "-b", f"{w},{s},{e},{n}", "-o", str(extract), str(self.pbf),
                ]  # fmt: skip
                try:
                    done = subprocess.run(cmd, capture_output=True, text=True)
                    if done.returncode != 0:
                        raise RuntimeError(f"osmium extract failed: {done.stderr.strip()}")
                    osmexport.export(extract, geojson)
                finally:
                    extract.unlink(missing_ok=True)
            self._memo[bounds] = list(osmexport.read_features(geojson))
        return self._memo[bounds]

    def features(self, layer: Layer, bounds: Bounds) -> list[Feature]:
        return self._all(bounds)  # the pipeline keeps what the layer's rules accept

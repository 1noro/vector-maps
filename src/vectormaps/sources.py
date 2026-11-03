"""Where the OSM data comes from: the Overpass API or a local PBF extract (ADR 0002).

Both give the same thing, features in lon/lat as (kind, tags, geometry), so the
rest of the program does not care which one was used.
"""

import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Protocol

from shapely.geometry.base import BaseGeometry

from vectormaps import osmexport, overpass
from vectormaps.layers import Layer

log = logging.getLogger(__name__)

Bounds = tuple[float, float, float, float]  # south, west, north, east
Feature = tuple[str, dict[str, str], BaseGeometry]


class Source(Protocol):
    def features(self, layer: Layer, bounds: Bounds) -> list[Feature]: ...


class OverpassSource:
    """One query per layer and area, cached on disk by the exact query."""

    def __init__(self, cache_dir: Path, url: str | None = None):
        self.cache_dir = cache_dir / "overpass"
        self.url = url

    def features(self, layer: Layer, bounds: Bounds) -> list[Feature]:
        osm = overpass.fetch(layer.overpass_query(bounds), self.cache_dir, self.url)
        geojson = osmexport.export(osm, osm.with_suffix(".geojsonseq"))
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
        self.cache_dir = cache_dir / "pbf"
        self._memo: dict[Bounds, list[Feature]] = {}

    def _key(self, bounds: Bounds) -> str:
        stat = self.pbf.stat()
        raw = f"{self.pbf.resolve()}|{stat.st_mtime_ns}|{stat.st_size}|{bounds}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    def _all(self, bounds: Bounds) -> list[Feature]:
        if bounds not in self._memo:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            key = self._key(bounds)
            extract = self.cache_dir / f"{key}.osm.pbf"
            geojson = self.cache_dir / f"{key}.geojsonseq"
            if not geojson.exists():
                s, w, n, e = bounds
                log.info("cutting %s with osmium", self.pbf.name)
                cmd = [
                    "osmium", "extract", "--overwrite", "--strategy=smart",
                    "-b", f"{w},{s},{e},{n}", "-o", str(extract), str(self.pbf),
                ]  # fmt: skip
                done = subprocess.run(cmd, capture_output=True, text=True)
                if done.returncode != 0:
                    raise RuntimeError(f"osmium extract failed: {done.stderr.strip()}")
                osmexport.export(extract, geojson)
                extract.unlink()
            self._memo[bounds] = list(osmexport.read_features(geojson))
        return self._memo[bounds]

    def features(self, layer: Layer, bounds: Bounds) -> list[Feature]:
        return self._all(bounds)  # the pipeline keeps what the layer's rules accept

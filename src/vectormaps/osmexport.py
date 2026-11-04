"""OSM data (XML or PBF) to shapely features, through `osmium export`.

osmium assembles the multipolygons for us, which is the hard part of OSM
geometry. Both sources of data (Overpass, local PBF) go through here.
"""

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from vectormaps.tmpfile import tmp_beside

# Bump when `export` changes what it writes: the cached files are named after it.
VERSION = "v2"  # v2: also points (place names)

KIND = {
    "Point": "point",
    "Polygon": "polygon",
    "MultiPolygon": "polygon",
    "LineString": "line",
}


def exported_name(osm_path: Path) -> Path:
    """Where the GeoJSON of `osm_path` is cached (next to it, tagged with the export version)."""
    return osm_path.parent / f"{osm_path.name.split('.')[0]}.{VERSION}.geojsonseq"


def export(osm_path: Path, out_path: Path) -> Path:
    """Run osmium; skip if already exported."""
    if out_path.exists():
        return out_path
    tmp = tmp_beside(out_path)
    cmd = [
        "osmium",
        "export",
        "--overwrite",
        "--geometry-types=point,linestring,polygon",
        "-f",
        "geojsonseq",
        "-o",
        str(tmp),
        str(osm_path),
    ]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError(f"osmium export failed: {done.stderr.strip()}")
        tmp.replace(out_path)
    finally:
        tmp.unlink(missing_ok=True)
    return out_path


def read_features(path: Path) -> Iterator[tuple[str, dict[str, str], BaseGeometry]]:
    """Yield (kind, tags, geometry), kind being 'point', 'line' or 'polygon'; lon/lat."""
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip("\x1e\n ")  # GeoJSON-seq may start records with RS
            if not line:
                continue
            feat = json.loads(line)
            kind = KIND.get(feat["geometry"]["type"])
            if kind is None:
                continue
            yield kind, feat.get("properties") or {}, shape(feat["geometry"])

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

KIND = {"Polygon": "polygon", "MultiPolygon": "polygon", "LineString": "line"}


def export(osm_path: Path, out_path: Path) -> Path:
    """Run osmium; skip if already exported."""
    if out_path.exists():
        return out_path
    tmp = out_path.with_suffix(".tmp")
    cmd = [
        "osmium",
        "export",
        "--overwrite",
        "--geometry-types=linestring,polygon",
        "-f",
        "geojsonseq",
        "-o",
        str(tmp),
        str(osm_path),
    ]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"osmium export failed: {done.stderr.strip()}")
    tmp.rename(out_path)
    return out_path


def read_features(path: Path) -> Iterator[tuple[str, dict[str, str], BaseGeometry]]:
    """Yield (kind, tags, geometry) with kind 'polygon' or 'line'. Coordinates in lon/lat."""
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

"""Administrative boundaries: from OSM relations to lines that know their levels.

In OSM a boundary is a relation (`boundary=administrative`, `admin_level=N`) whose
member ways are the line; the ways themselves rarely carry the level. And a way is
often the edge of several units at once (a parish, its municipality, the province).
So each member way comes out once, as a line tagged with every level it bounds
(`LEVELS_TAG = "4;6;8"`); the pipeline draws it as the highest of those that the map
shows. Only the ways in the data are needed: never the whole relation, which for a
country is megabytes outside the map.
"""

import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

from shapely.geometry import LineString

from vectormaps.tmpfile import tmp_beside

LEVELS_TAG = "vectormaps:admin_levels"
LEVELS = range(2, 11)  # 2 country … 10 the smallest local units (parishes in Galicia)


def _skip(tags: dict[str, str]) -> bool:
    """Edges along the sea: the coastline or the sea limit draw it, not a boundary."""
    return tags.get("maritime") == "yes" or tags.get("natural") == "coastline"


def parse(osm_xml: Path) -> Iterator[tuple[set[int], LineString]]:
    """(levels, line in lon/lat) for every way of a boundary relation in the file."""
    nodes: dict[str, tuple[float, float]] = {}
    ways: dict[str, tuple[list[str], dict[str, str]]] = {}
    levels: dict[str, set[int]] = {}
    for _event, el in ET.iterparse(osm_xml):
        if el.tag == "node":
            nodes[el.get("id")] = (float(el.get("lon")), float(el.get("lat")))
        elif el.tag == "way":
            refs = [nd.get("ref") for nd in el.iter("nd")]
            ways[el.get("id")] = (refs, {t.get("k"): t.get("v") for t in el.iter("tag")})
        elif el.tag == "relation":
            tags = {t.get("k"): t.get("v") for t in el.iter("tag")}
            level = tags.get("admin_level", "")
            if tags.get("boundary") == "administrative" and level.isdigit():
                for m in el.iter("member"):
                    if m.get("type") == "way":
                        levels.setdefault(m.get("ref"), set()).add(int(level))
        else:
            continue
        el.clear()
    for way, found in levels.items():
        if way not in ways or not (found := found & set(LEVELS)):
            continue
        refs, tags = ways[way]
        coords = [nodes[r] for r in refs if r in nodes]
        if len(coords) >= 2 and not _skip(tags):
            yield found, LineString(coords)


def features(osm_path: Path) -> Iterator[dict]:
    """The boundary lines of an OSM file (XML or PBF) as GeoJSON features.

    `osmium tags-filter` keeps the boundary relations and the ways and nodes of
    theirs that the file has, as XML; that is small enough to read here.
    """
    small = tmp_beside(osm_path.with_name("boundaries.osm"))
    cmd = ["osmium", "tags-filter", "--overwrite", "-o", str(small), str(osm_path)]
    try:
        done = subprocess.run(cmd + ["r/boundary=administrative"], capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError(f"osmium tags-filter failed: {done.stderr.strip()}")
        for found, line in parse(small):
            yield {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": list(line.coords)},
                "properties": {LEVELS_TAG: ";".join(str(n) for n in sorted(found))},
            }
    finally:
        small.unlink(missing_ok=True)

"""Which Geofabrik extract covers an area, to suggest one when Overpass fails.

Geofabrik publishes an index of its extracts with their outlines (~4 MB). It is
fetched once, only when needed (one request, our User-Agent, no account or key),
and kept in the cache; `make clean-cache` refreshes it.
"""

import http.client
import json
import logging
import urllib.request
from pathlib import Path
from typing import NamedTuple

from shapely.geometry import MultiPolygon, box, shape

from vectormaps.download import USER_AGENT
from vectormaps.tmpfile import tmp_beside

log = logging.getLogger(__name__)

INDEX_URL = "https://download.geofabrik.de/index-v1.json"
TIMEOUT = 30


class Region(NamedTuple):
    name: str
    url: str  # of the .osm.pbf

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def _index(cache_dir: Path) -> dict | None:
    path = cache_dir / "geofabrik" / "index-v1.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    req = urllib.request.Request(INDEX_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = resp.read()
        index = json.loads(data)
    except (OSError, http.client.HTTPException, ValueError) as err:
        log.warning("cannot get the Geofabrik index: %s", err)
        return None  # just a hint: the caller says something generic instead
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp_beside(path)
    try:
        tmp.write_bytes(data)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return index


def region_for(areas: list[tuple[float, float, float, float]], cache_dir: Path) -> Region | None:
    """The smallest Geofabrik extract that holds every one of the (south, west, north, east)."""
    index = _index(cache_dir)
    if index is None:
        return None
    # Each area on its own: the box around two zones may reach into another country.
    area = MultiPolygon([box(w, s, e, n) for s, w, n, e in areas])
    best: tuple[float, Region] | None = None
    for feat in index.get("features", []):
        props = feat.get("properties") or {}
        url = (props.get("urls") or {}).get("pbf")
        if not url or not feat.get("geometry"):
            continue
        outline = shape(feat["geometry"])
        if outline.contains(area) and (best is None or outline.area < best[0]):
            best = outline.area, Region(props.get("name") or props.get("id", "?"), url)
    return best[1] if best else None

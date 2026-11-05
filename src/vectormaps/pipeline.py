"""Glue between a frame, the layers and a data source: gives items per layer."""

import logging
from pathlib import Path
from typing import NamedTuple

import shapely
from shapely.geometry import MultiLineString
from shapely.geometry.base import BaseGeometry

from vectormaps import relief
from vectormaps.area import Frame
from vectormaps.boundaries import LEVELS_TAG
from vectormaps.labels import pick_name
from vectormaps.layers import Layer
from vectormaps.overpass import OverpassError
from vectormaps.progress import Spinner
from vectormaps.sources import Source

log = logging.getLogger(__name__)

LARGE_AREA_DEG2 = 0.04  # ~ 20 x 20 km at mid latitudes: too much for the public Overpass


class Item(NamedTuple):
    """One thing to draw: its class (what a theme styles), its lon/lat geometry and, for
    the label layers, the text to write and its rank in the class (lower first, see
    `Layer.match`); for the hillshade, the map's DEM instead."""

    cls: str
    geom: BaseGeometry | None
    text: str | None = None
    raster: Path | None = None
    rank: int = 0


Features = dict[str, list[Item]]  # layer name -> items


def _osm(layer: Layer, features: list, langs: list[str]) -> list[Item]:
    items = []
    for kind, tags, geom in features:
        found = layer.match(kind, tags)
        if found is None:
            continue
        cls, rank = found
        text = pick_name(tags, langs) if layer.text else None
        if layer.text and text is None:
            continue
        items.append(Item(cls, geom, text, rank=rank))
    return items


def _boundaries(layer: Layer, features: list, drawn: set[int]) -> list[Item]:
    """The boundary lines this layer draws: each edge as the highest level (the lowest
    admin_level) it bounds among those on the map, so a shared edge is drawn once, by
    the most important layer present, and every layer stays closed without the others."""
    classes = dict(layer.admin)
    lines: dict[str, list] = {}
    for kind, tags, geom in features:
        if kind != "line" or LEVELS_TAG not in tags:
            continue
        levels = {int(n) for n in tags[LEVELS_TAG].split(";")} & drawn
        cls = classes.get(min(levels)) if levels else None
        if cls is not None:
            lines.setdefault(cls, []).append(geom)
    # The ways of a class joined end to end: the dashes run on from one to the next.
    return [Item(cls, shapely.line_merge(MultiLineString(ls))) for cls, ls in lines.items()]


def _relief(frame: Frame, layer: Layer, cache: Path) -> list[Item]:
    dem = relief.frame_dem(frame, cache / "dem")
    if dem is None:
        return []  # open sea
    if layer.name == "hillshade":
        return [Item("shade", None, raster=dem)]  # the theme says how to draw it
    return [Item(cls, line) for cls, _elev, line in relief.contours(frame, dem)]


def load_features(
    frame: Frame,
    layers: list[Layer],
    source: Source,
    langs: list[str] | None = None,
    cache: Path = Path("data/cache"),
) -> Features:
    langs = langs or ["es"]
    bounds = frame.lonlat_bounds()
    south, west, north, east = bounds
    if (north - south) * (east - west) > LARGE_AREA_DEG2:
        log.warning("large area: the public Overpass may time out; a local PBF copes better")

    drawn = {level for layer in layers for level, _cls in layer.admin}
    out: Features = {}
    for n, layer in enumerate(layers, 1):
        origin = "Copernicus DEM" if layer.dem else source.name
        # Step n of the total: Overpass gives no size or progress, so no percentage.
        # "loading", not "downloading": the cache or a local extract download nothing.
        with Spinner(f"loading layer {n}/{len(layers)}: {layer.name}, from {origin}"):
            if layer.dem:
                items = _relief(frame, layer, cache)
            else:
                try:
                    feats = source.features(layer, bounds)
                    if layer.admin:
                        items = _boundaries(layer, feats, drawn)
                    else:
                        items = _osm(layer, feats, langs)
                except OverpassError as err:
                    raise OverpassError(f"layer {layer.name}: {err}") from err
        log.info("layer %s: %d features (%s)", layer.name, len(items), origin)
        out[layer.name] = items
    if not any(out.values()):
        log.warning("no data found in this area; is it covered by the data source?")
    return out

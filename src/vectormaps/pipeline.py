"""Glue between a frame, the layers and a data source: gives items per layer."""

import logging
from pathlib import Path
from typing import NamedTuple

from shapely.geometry.base import BaseGeometry

from vectormaps import relief
from vectormaps.area import Frame
from vectormaps.labels import pick_name
from vectormaps.layers import Layer
from vectormaps.overpass import OverpassError
from vectormaps.progress import Spinner
from vectormaps.sources import Source

log = logging.getLogger(__name__)

LARGE_AREA_DEG2 = 0.04  # ~ 20 x 20 km at mid latitudes: too much for the public Overpass


class Item(NamedTuple):
    """One thing to draw: its class (what a theme styles), its lon/lat geometry and, for
    the label layers, the text to write; for the hillshade, the raster instead."""

    cls: str
    geom: BaseGeometry | None
    text: str | None = None
    raster: Path | None = None


Features = dict[str, list[Item]]  # layer name -> items


def _osm(layer: Layer, features: list, langs: list[str]) -> list[Item]:
    items = []
    for kind, tags, geom in features:
        cls = layer.classify(kind, tags)
        if cls is None:
            continue
        text = pick_name(tags, langs) if layer.text else None
        if layer.text and text is None:
            continue
        items.append(Item(cls, geom, text))
    return items


def _relief(frame: Frame, layer: Layer, cache: Path) -> list[Item]:
    dem = relief.frame_dem(frame, cache / "dem")
    if dem is None:
        return []  # open sea
    if layer.name == "hillshade":
        return [Item("shade", None, raster=relief.hillshade(dem))]
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

    out: Features = {}
    for layer in layers:
        with Spinner(f"layer {layer.name}"):
            if layer.dem:
                items = _relief(frame, layer, cache)
            else:
                try:
                    items = _osm(layer, source.features(layer, bounds), langs)
                except OverpassError as err:
                    raise OverpassError(f"layer {layer.name}: {err}") from err
        origin = "Copernicus DEM" if layer.dem else source.name
        log.info("layer %s: %d features (%s)", layer.name, len(items), origin)
        out[layer.name] = items
    if not any(out.values()):
        log.warning("no data found in this area; is it covered by the data source?")
    return out

"""Glue between a frame, the layers and a data source: gives items per layer."""

import logging
from typing import NamedTuple

from shapely.geometry.base import BaseGeometry

from vectormaps.area import Frame
from vectormaps.labels import pick_name
from vectormaps.layers import Layer
from vectormaps.progress import Spinner
from vectormaps.sources import Source

log = logging.getLogger(__name__)

LARGE_AREA_DEG2 = 0.04  # ~ 20 x 20 km at mid latitudes: too much for the public Overpass


class Item(NamedTuple):
    """One thing to draw: its class (what a theme styles), its lon/lat geometry and, for
    the label layers, the text to write."""

    cls: str
    geom: BaseGeometry
    text: str | None = None


Features = dict[str, list[Item]]  # layer name -> items


def load_features(
    frame: Frame, layers: list[Layer], source: Source, langs: list[str] | None = None
) -> Features:
    langs = langs or ["es"]
    bounds = frame.lonlat_bounds()
    south, west, north, east = bounds
    if (north - south) * (east - west) > LARGE_AREA_DEG2:
        log.warning("large area: the public Overpass may time out; a local PBF copes better")

    out: Features = {}
    for layer in layers:
        with Spinner(f"layer {layer.name}"):
            items = []
            for kind, tags, geom in source.features(layer, bounds):
                cls = layer.classify(kind, tags)
                if cls is None:
                    continue
                text = pick_name(tags, langs) if layer.text else None
                if layer.text and text is None:
                    continue
                items.append(Item(cls, geom, text))
        log.info("layer %s: %d features", layer.name, len(items))
        out[layer.name] = items
    if not any(out.values()):
        log.warning("no data found in this area; is it covered by the data source?")
    return out

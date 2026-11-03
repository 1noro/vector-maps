"""Glue between a frame, the layers and a data source: gives features per layer."""

import logging

from shapely.geometry.base import BaseGeometry

from vectormaps.area import Frame
from vectormaps.layers import Layer
from vectormaps.sources import Source

log = logging.getLogger(__name__)

# layer name -> [(class, geometry in lon/lat)]
Features = dict[str, list[tuple[str, BaseGeometry]]]

LARGE_AREA_DEG2 = 0.04  # ~ 20 x 20 km at mid latitudes: too much for the public Overpass


def load_features(frame: Frame, layers: list[Layer], source: Source) -> Features:
    bounds = frame.lonlat_bounds()
    south, west, north, east = bounds
    if (north - south) * (east - west) > LARGE_AREA_DEG2:
        log.warning("large area: the public Overpass may time out; a local PBF copes better")

    out: Features = {}
    for layer in layers:
        log.info("layer %s", layer.name)
        feats = []
        for kind, tags, geom in source.features(layer, bounds):
            cls = layer.classify(kind, tags)
            if cls is not None:
                feats.append((cls, geom))
        log.info("  %d features", len(feats))
        out[layer.name] = feats
    return out

"""Features to an SVG: units in mm, one Inkscape layer per area and per OSM layer.

Several areas can be stacked on the same page (the overlay): each one is a
`Job`, drawn on top of the previous one, with its own scale, theme and opacity.
"""

from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr

import numpy as np
import shapely
from pyproj import Transformer
from shapely.affinity import affine_transform
from shapely.geometry.base import BaseGeometry

from vectormaps.area import Frame
from vectormaps.layers import Layer
from vectormaps.pipeline import Features
from vectormaps.theme import Theme

MIN_POLYGON_MM2 = 0.005  # below this a polygon is a speck on paper


@dataclass
class Job:
    label: str  # "a", "b": ids in the SVG
    frame: Frame
    theme: Theme
    layers: list[Layer]
    features: Features
    opacity: float = 1.0


def _num(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def _parts(geom: BaseGeometry):
    if hasattr(geom, "geoms"):
        for g in geom.geoms:
            yield from _parts(g)
    else:
        yield geom


def _coords(coords) -> str:
    return " ".join(f"{_num(x)} {_num(y)}" for x, y in coords)


def path_data(geoms: list[BaseGeometry]) -> str:
    """SVG path `d` for polygons (closed rings, use evenodd) and lines."""
    d: list[str] = []
    for geom in geoms:
        for part in _parts(geom):
            if part.geom_type == "Polygon":
                if part.area < MIN_POLYGON_MM2:
                    continue
                for ring in (part.exterior, *part.interiors):
                    d.append(f"M{_coords(ring.coords[:-1])}Z")
            elif part.geom_type == "LineString" and len(part.coords) >= 2:
                d.append(f"M{_coords(part.coords)}")
    return "".join(d)


def _to_page(geom: BaseGeometry, tr: Transformer, frame: Frame) -> BaseGeometry | None:
    def project(coords: np.ndarray) -> np.ndarray:
        x, y = tr.transform(coords[:, 0], coords[:, 1])
        return np.column_stack((x, y))

    geom = affine_transform(shapely.transform(geom, project), frame.page_matrix())
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    m = frame.margin
    clipped = shapely.clip_by_rect(geom, m, m, frame.page_w - m, frame.page_h - m)
    return None if clipped.is_empty else clipped


def _attrs(style: dict[str, str | float]) -> str:
    return " ".join(f"{k}={quoteattr(str(v))}" for k, v in style.items())


def _job_group(job: Job) -> str:
    tr = Transformer.from_crs(4326, job.frame.crs, always_xy=True)
    label = f"{job.label.upper()} 1:{job.frame.scale} {job.theme.name}"
    opacity = f' opacity="{job.opacity:g}"' if job.opacity < 1 else ""
    out = [
        f'<g id="area-{job.label}" inkscape:groupmode="layer" '
        f"inkscape:label={quoteattr(label)}{opacity}>"
    ]
    for layer in job.layers:
        out.append(
            f'<g id="{job.label}-{layer.name}" inkscape:groupmode="layer" '
            f'inkscape:label="{layer.name}">'
        )
        by_class: dict[str, list[BaseGeometry]] = {c: [] for c in layer.classes}
        for cls, geom in job.features.get(layer.name, []):
            page_geom = _to_page(geom, tr, job.frame)
            if page_geom is not None:
                by_class[cls].append(page_geom)
        for cls in layer.classes:
            d = path_data(by_class[cls])
            if not d:
                continue
            style = job.theme.style(layer.name, cls)
            out.append(
                f'<path id="{job.label}-{layer.name}-{cls}" class="{cls}" '
                f'fill-rule="evenodd" {_attrs(style)} d="{d}"/>'
            )
        out.append("</g>")
    out.append("</g>")
    return "\n".join(out)


def render(jobs: list[Job]) -> str:
    first = jobs[0]
    f = first.frame
    page = first.theme.page
    ink = page["ink"]
    attribution = "© OpenStreetMap contributors (ODbL)"
    scales = " + ".join(f"{j.label.upper()} 1:{j.frame.scale}" for j in jobs)
    footer = f"{attribution} · {f.paper} {f.orientation} · {scales}"
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" version="1.1" '
        f'width="{_num(f.page_w)}mm" height="{_num(f.page_h)}mm" '
        f'viewBox="0 0 {_num(f.page_w)} {_num(f.page_h)}">',
        f"<title>{escape(footer)}</title>",
        '<g id="page" inkscape:groupmode="layer" inkscape:label="page">',
        f'<rect width="{_num(f.page_w)}" height="{_num(f.page_h)}" fill="{page["background"]}"/>',
        "</g>",
    ]
    parts += [_job_group(j) for j in jobs]
    parts += [
        '<g id="frame" inkscape:groupmode="layer" inkscape:label="frame">',
        f'<rect x="{_num(f.margin)}" y="{_num(f.margin)}" width="{_num(f.map_w)}" '
        f'height="{_num(f.map_h)}" fill="none" stroke="{ink}" '
        f'stroke-width="{page["frame-width"]}"/>',
        f'<text x="{_num(f.margin)}" y="{_num(f.page_h - f.margin / 2 + 0.9)}" '
        f'font-family="sans-serif" font-size="2.5" fill="{ink}">{escape(footer)}</text>',
        "</g>",
        "</svg>",
    ]
    return "\n".join(parts) + "\n"

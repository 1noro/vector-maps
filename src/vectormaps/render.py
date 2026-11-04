"""Features to an SVG: units in mm, one Inkscape layer per area and per OSM layer.

Several areas can be stacked on the same page (the overlay): each one is a
`Job`, drawn on top of the previous one, with its own scale, theme and opacity.
"""

import base64
from dataclasses import dataclass
from xml.sax.saxutils import escape, quoteattr

import numpy as np
import shapely
from pyproj import Transformer
from shapely.affinity import affine_transform
from shapely.geometry import LineString, Point, box
from shapely.geometry.base import BaseGeometry

from vectormaps import relief
from vectormaps.area import Frame
from vectormaps.labels import CHAR_WIDTH, street_pieces, text_width
from vectormaps.layers import Layer
from vectormaps.pipeline import Features
from vectormaps.theme import PATTERN_PREFIX, Theme

MIN_POLYGON_MM2 = 0.005  # below this a polygon is a speck on paper
MARK = "Generated with vector-maps by 1noro"
ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"
SHORT_ATTRIBUTION = "© OpenStreetMap"  # the short form OSM accepts; the minimal legend keeps it
LEGENDS = ("full", "minimal")
COORDS = ("dd", "dm", "dms")  # decimal degrees, degrees and decimal minutes, d-m-s
LEGEND_SIZE = 2.4  # mm; smaller on small margins or long lines, so everything fits


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
    x0, y0 = frame.map_x, frame.map_y
    clipped = shapely.clip_by_rect(geom, x0, y0, x0 + frame.map_w, y0 + frame.map_h)
    return None if clipped.is_empty else clipped


def _attrs(style: dict[str, str | float]) -> str:
    return " ".join(f"{k}={quoteattr(str(v))}" for k, v in style.items())


def _with_patterns(style: dict[str, str | float], label: str) -> dict[str, str | float]:
    """`pattern:<name>` as the url of that zone's `<pattern>`."""
    return {
        k: f"url(#{_pattern_id(label, v.removeprefix(PATTERN_PREFIX))})"
        if isinstance(v, str) and v.startswith(PATTERN_PREFIX)
        else v
        for k, v in style.items()
    }


def _pattern_id(label: str, name: str) -> str:
    return f"{label}-pattern-{name}"


def _pattern(pid: str, p: dict[str, str | float]) -> str:
    """A tile in mm, repeated over the fill: parallel lines (dashed or not) or dots."""
    s = float(p["spacing"])
    colour = quoteattr(str(p.get("color", "#000000")))
    if p["kind"] == "lines":
        dash = float(p.get("dash", 0))
        w = 2 * dash if dash else s
        mark = (
            f'<line x1="0" y1="{_num(s / 2)}" x2="{_num(dash or w)}" y2="{_num(s / 2)}" '
            f'stroke={colour} stroke-width="{p.get("width", 0.1)}"/>'
        )
    else:  # dots
        w = s
        r = _num(float(p.get("radius", s / 6)))
        mark = f'<circle cx="{_num(s / 2)}" cy="{_num(s / 2)}" r="{r}" fill={colour}/>'
    background = p.get("background")
    rect = (
        f'<rect width="{_num(w)}" height="{_num(s)}" fill={quoteattr(str(background))}/>'
        if background
        else ""
    )
    angle = float(p.get("angle", 0))
    rotate = f' patternTransform="rotate({angle:g})"' if angle else ""
    return (
        f'<pattern id="{pid}" patternUnits="userSpaceOnUse" width="{_num(w)}" '
        f'height="{_num(s)}"{rotate}>{rect}{mark}</pattern>'
    )


def _pattern_defs(job: Job) -> str:
    """The `<pattern>`s this zone's shape layers use, once each."""
    used: list[str] = []
    for layer in job.layers:
        if layer.text or layer.name == "hillshade":
            continue
        for cls in layer.classes:
            for v in job.theme.style(layer.name, cls).values():
                name = v.removeprefix(PATTERN_PREFIX) if isinstance(v, str) else ""
                if isinstance(v, str) and v.startswith(PATTERN_PREFIX) and name not in used:
                    used.append(name)
    return "".join(_pattern(_pattern_id(job.label, n), job.theme.patterns[n]) for n in used)


def _shape_layer(job: Job, layer: Layer, tr: Transformer) -> list[str]:
    by_class: dict[str, list[BaseGeometry]] = {c: [] for c in layer.classes}
    for item in job.features.get(layer.name, []):
        page_geom = _to_page(item.geom, tr, job.frame)
        if page_geom is not None:
            by_class[item.cls].append(page_geom)
    casings, out = [], []
    for cls in layer.classes:
        d = path_data(by_class[cls])
        if not d:
            continue
        style = _with_patterns(job.theme.style(layer.name, cls), job.label)
        casing = _casing(style)
        if casing:
            casings.append(
                f'<path id="{job.label}-{layer.name}-{cls}-casing" class="{cls} casing" '
                f'{_attrs(casing)} d="{d}"/>'
            )
        out.append(
            f'<path id="{job.label}-{layer.name}-{cls}" class="{cls}" '
            f'fill-rule="evenodd" {_attrs(style)} d="{d}"/>'
        )
    # Every casing under every line: where two streets meet, their outlines do not cut them.
    return casings + out


def _casing(style: dict[str, str | float]) -> dict[str, str | float] | None:
    """The outline under a line: the same line, `casing-width` mm wider on each side.

    Takes the casing keys out of `style`, which are not SVG attributes.
    """
    width = style.pop("casing-width", None)
    colour = style.pop("casing-color", None)
    if not width or not colour:
        return None
    casing = {
        k: v for k, v in style.items() if k in ("stroke-linecap", "stroke-linejoin", "opacity")
    }
    return {
        "fill": "none",
        "stroke": colour,
        "stroke-width": _num(float(style.get("stroke-width", 0)) + 2 * float(width)),
        **casing,
    }


def _hillshade_layer(job: Job, layer: Layer) -> list[str]:
    """The shade as a PNG over the map rectangle; the DEM grid is aligned with it."""
    style = dict(job.theme.style(layer.name, "shade"))
    shadow = str(style.pop("shadow", "#000000"))
    highlight = str(style.pop("highlight", "#ffffff"))
    f = job.frame
    out = []
    for item in job.features.get(layer.name, []):
        if item.raster is None:
            continue
        png = base64.b64encode(relief.shade_png(item.raster, shadow, highlight)).decode()
        out.append(
            f'<image id="{job.label}-{layer.name}-shade" class="shade" {_attrs(style)} '
            f'x="{_num(f.map_x)}" y="{_num(f.map_y)}" width="{_num(f.map_w)}" '
            f'height="{_num(f.map_h)}" preserveAspectRatio="none" '
            f'xlink:href="data:image/png;base64,{png}"/>'
        )
    return out


def _page_xy(geom: BaseGeometry, tr: Transformer, frame: Frame) -> tuple[float, float] | None:
    """A point in page mm, or None if it falls outside the map frame."""
    x, y = tr.transform(geom.x, geom.y)
    a, _, _, e, xoff, yoff = frame.page_matrix()
    x, y = a * x + xoff, e * y + yoff
    x0, y0 = frame.map_x, frame.map_y
    inside = x0 <= x <= x0 + frame.map_w and y0 <= y <= y0 + frame.map_h
    return (x, y) if inside else None


def _map_area(frame: Frame, inset: float = 0.0) -> BaseGeometry:
    """The drawn part of the page (the rectangle, or the circle), `inset` mm smaller all round."""
    x0, y0, w, h = frame.map_x, frame.map_y, frame.map_w, frame.map_h
    if frame.shape == "circle":
        return Point(x0 + w / 2, y0 + h / 2).buffer(max(w / 2 - inset, 0), quad_segs=32)
    return box(x0 + inset, y0 + inset, x0 + w - inset, y0 + h - inset)


def _place_box(x: float, y: float, text: str, style: dict) -> BaseGeometry:
    """Where a name written at (x, y) goes on the page, halo included; widths on the high side."""
    size = float(style["font-size"])
    w = text_width(text, size) + len(text) * float(style.get("letter-spacing", 0))
    anchor = style.get("text-anchor", "start")
    x0 = x - w / 2 if anchor == "middle" else x - w if anchor == "end" else x
    halo = float(style.get("stroke-width", 0)) / 2
    # From the baseline: capitals reach ~0.75 em up, descenders ~0.25 em down.
    return box(x0 - halo, y - 0.8 * size - halo, x0 + w + halo, y + 0.25 * size + halo)


def _text_layer(job: Job, layer: Layer, tr: Transformer) -> list[str]:
    """Labels: names of places at their point, names of streets written along the street.

    No letter goes past the edge of the map: a place name that does not fit is left out
    (moved, it would no longer point at its place), and a street name is only written on
    the stretch that is half a letter and the halo away from the edge.
    """
    defs: list[str] = []
    groups: list[str] = []
    whole = _map_area(job.frame)
    for cls in layer.classes:
        style = job.theme.style(layer.name, cls)
        size = float(style["font-size"])
        inner = _map_area(job.frame, size / 2 + float(style.get("stroke-width", 0)) / 2)
        lines: dict[str, list[LineString]] = {}
        texts: list[str] = []
        for item in job.features.get(layer.name, []):
            if item.cls != cls or not item.text:
                continue
            if item.geom.geom_type == "Point":
                xy = _page_xy(item.geom, tr, job.frame)
                if xy is not None and _place_box(*xy, item.text, style).within(whole):
                    texts.append(
                        f'<text x="{_num(xy[0])}" y="{_num(xy[1])}">{escape(item.text)}</text>'
                    )
                continue
            page_geom = _to_page(item.geom, tr, job.frame)
            if page_geom is not None:
                lines.setdefault(item.text, []).extend(
                    p
                    for p in _parts(page_geom.intersection(inner))
                    if p.geom_type == "LineString" and not p.is_empty
                )
        n = 0
        for text, parts in sorted(lines.items()):
            for piece in street_pieces(parts, text, size) if parts else []:
                n += 1
                pid = f"{job.label}-{layer.name}-{cls}-{n}"
                defs.append(f'<path id="{pid}" d="M{_coords(piece.coords)}"/>')
                texts.append(
                    f'<text dy="0.35em"><textPath xlink:href="#{pid}" startOffset="50%" '
                    f'text-anchor="middle">{escape(text)}</textPath></text>'
                )
        if texts:
            groups.append(
                f'<g id="{job.label}-{layer.name}-{cls}" class="{cls}" {_attrs(style)}>'
                + "".join(texts)
                + "</g>"
            )
    return (["<defs>" + "".join(defs) + "</defs>"] if defs else []) + groups


def _job_group(job: Job) -> str:
    tr = Transformer.from_crs(4326, job.frame.crs, always_xy=True)
    label = f"{job.label.upper()} 1:{job.frame.scale} {job.theme.name}"
    opacity = f' opacity="{job.opacity:g}"' if job.opacity < 1 else ""
    f = job.frame
    # Every zone is clipped to the map: the geometry is cut at the edge, but a round
    # line end, a casing or a stroke along the edge would still reach past it by half a width.
    if f.shape == "circle":
        shape = (
            f'<circle cx="{_num(f.page_w / 2)}" cy="{_num(f.page_h / 2)}" r="{_num(f.map_w / 2)}"/>'
        )
    else:
        shape = (
            f'<rect x="{_num(f.map_x)}" y="{_num(f.map_y)}" '
            f'width="{_num(f.map_w)}" height="{_num(f.map_h)}"/>'
        )
    out = [
        f'<g id="area-{job.label}" inkscape:groupmode="layer" '
        f'inkscape:label={quoteattr(label)}{opacity} clip-path="url(#clip-{job.label})">',
        f'<defs><clipPath id="clip-{job.label}">{shape}</clipPath>{_pattern_defs(job)}</defs>',
    ]
    for layer in job.layers:
        out.append(
            f'<g id="{job.label}-{layer.name}" inkscape:groupmode="layer" '
            f'inkscape:label="{layer.name}">'
        )
        if layer.text:
            out += _text_layer(job, layer, tr)
        elif layer.name == "hillshade":
            out += _hillshade_layer(job, layer)
        else:
            out += _shape_layer(job, layer, tr)
        out.append("</g>")
    out.append("</g>")
    return "\n".join(out)


def _dms(value: float, axis: str, fmt: str) -> str:
    """One coordinate as degrees, minutes and seconds (or decimal minutes), with its hemisphere."""
    hemi = ("N" if value >= 0 else "S") if axis == "lat" else ("E" if value >= 0 else "W")
    v = abs(value)
    if fmt == "dm":  # whole thousandths of a minute, so 59.9996' carries into the degree
        total = round(v * 60000)
        return f"{total // 60000}°{total % 60000 / 1000:06.3f}'{hemi}"
    total = round(v * 36000)  # tenths of a second (~3 m)
    return f"{total // 36000}°{total // 600 % 60:02d}'{total % 600 / 10:04.1f}\"{hemi}"


def _corner(c: tuple[float, float], coords: str = "dd") -> str:
    """A (lat, lon) as the legend writes it, in the format `coords` (COORDS)."""
    if coords == "dd":
        return f"{c[0]:.5f}, {c[1]:.5f}"
    return f"{_dms(c[0], 'lat', coords)} {_dms(c[1], 'lon', coords)}"


def legend_lines(jobs: list[Job], legend: str = "full", coords: str = "dd") -> tuple[str, ...]:
    """The bottom lines of the legend.

    Full: attribution, paper and scales; then the corners. Minimal: one line with the
    corners, the scales and the short attribution (ODbL asks for it on every map).
    """
    if legend not in LEGENDS:
        raise ValueError(f"unknown legend {legend!r}; use {', '.join(LEGENDS)}")
    if coords not in COORDS:
        raise ValueError(f"unknown coordinate format {coords!r}; use {', '.join(COORDS)}")
    f = jobs[0].frame
    # The zone letter only tells them apart when there are several.
    scales = " + ".join(
        f"{j.label.upper() + ' ' if len(jobs) > 1 else ''}1:{j.frame.scale}" for j in jobs
    )
    zones = []
    for j in jobs:
        prefix = f"{j.label.upper()}: " if len(jobs) > 1 else ""
        if j.frame.shape == "circle":  # a circle has no corners: say where its middle is
            zones.append(f"{prefix}⌖ {_corner(j.frame.center(), coords)}")
        else:
            tl, br = j.frame.corners()
            zones.append(f"{prefix}↖ {_corner(tl, coords)} · ↘ {_corner(br, coords)}")
    corners = "   |   ".join(zones)
    if legend == "minimal":
        return (f"{corners} · {scales} · {SHORT_ATTRIBUTION}",)
    return f"{ATTRIBUTION} · {f.paper} {f.orientation} · {scales}", corners


def uses_relief(jobs: list[Job]) -> bool:
    return any(j.features.get(layer.name) for j in jobs for layer in j.layers if layer.dem)


def _legend(jobs: list[Job], ink: str, legend: str, coords: str) -> list[str]:
    f = jobs[0].frame
    lines = legend_lines(jobs, legend, coords)
    # The relief's attribution (its licence asks for it) goes top left, beside the mark.
    top = relief.ATTRIBUTION if uses_relief(jobs) else ""
    widest = max(*(len(line) for line in lines), len(top) + len(MARK) + 4)
    size = min(LEGEND_SIZE, f.margin / 3, f.print_w / (widest * CHAR_WIDTH))
    # The lines centred in the bottom margin, the mark centred in the top one.
    pad = (f.margin - size - (len(lines) - 1) * 1.35 * size) / 2
    y1 = f.page_h - f.margin + pad + 0.85 * size
    common = f'font-family="sans-serif" font-size="{_num(size)}" fill="{ink}"'
    return [
        '<g id="legend" inkscape:groupmode="layer" inkscape:label="legend">',
        *(
            f'<text x="{_num(f.margin)}" y="{_num(y1 + i * 1.35 * size)}" {common}>'
            f"{escape(line)}</text>"
            for i, line in enumerate(lines)
        ),
        f'<text x="{_num(f.page_w - f.margin)}" y="{_num(f.margin / 2 + 0.35 * size)}" '
        f'text-anchor="end" {common}>{escape(MARK)}</text>',
        *(
            [
                f'<text x="{_num(f.margin)}" y="{_num(f.margin / 2 + 0.35 * size)}" {common}>'
                f"{escape(top)}</text>"
            ]
            if top
            else []
        ),
        "</g>",
    ]


def _credits(jobs: list[Job]) -> tuple[str, ...]:
    return ((relief.ATTRIBUTION,) if uses_relief(jobs) else ()) + (MARK,)


def _outline(f: Frame, ink: str, width: float | str) -> str:
    if f.shape == "circle":
        return (
            f'<circle cx="{_num(f.page_w / 2)}" cy="{_num(f.page_h / 2)}" '
            f'r="{_num(f.map_w / 2)}" fill="none" stroke="{ink}" stroke-width="{width}"/>'
        )
    return (
        f'<rect x="{_num(f.map_x)}" y="{_num(f.map_y)}" width="{_num(f.map_w)}" '
        f'height="{_num(f.map_h)}" fill="none" stroke="{ink}" stroke-width="{width}"/>'
    )


def render(jobs: list[Job], legend: str = "full", coords: str = "dd") -> str:
    first = jobs[0]
    f = first.frame
    page = first.theme.page
    ink = page["ink"]
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" '
        f'width="{_num(f.page_w)}mm" height="{_num(f.page_h)}mm" '
        f'viewBox="0 0 {_num(f.page_w)} {_num(f.page_h)}">',
        f"<title>{escape(' — '.join(legend_lines(jobs, legend, coords) + _credits(jobs)))}</title>",
        '<g id="page" inkscape:groupmode="layer" inkscape:label="page">',
        f'<rect width="{_num(f.page_w)}" height="{_num(f.page_h)}" fill="{page["background"]}"/>',
        "</g>",
    ]
    parts += [_job_group(j) for j in jobs]
    parts += [
        '<g id="frame" inkscape:groupmode="layer" inkscape:label="frame">',
        _outline(f, ink, page["frame-width"]),
        "</g>",
        *_legend(jobs, ink, legend, coords),
        "</svg>",
    ]
    return "\n".join(parts) + "\n"

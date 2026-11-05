"""Features to an SVG: units in mm, one Inkscape layer per area and per OSM layer.

Several areas can be stacked on the same page (the overlay): each one is a
`Job`, drawn on top of the previous one, with its own scale, theme and opacity.
"""

import base64
import math
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import numpy as np
import shapely
from pyproj import Transformer
from shapely.affinity import affine_transform
from shapely.geometry import LineString, Point, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import polylabel

from vectormaps import relief
from vectormaps.area import Frame
from vectormaps.labels import CHAR_WIDTH, Placer, street_slots, text_width
from vectormaps.layers import LABEL_PRIORITY, Layer
from vectormaps.pipeline import Features
from vectormaps.theme import PATTERN_PREFIX, Theme

MIN_POLYGON_MM2 = 0.005  # below this a polygon is a speck on paper
MARK = "Generated with vector-maps by 1noro"
ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"
SHORT_ATTRIBUTION = "© OpenStreetMap"  # the short form OSM accepts; the minimal legend keeps it
LEGENDS = ("full", "minimal")
COORDS = ("dd", "dm", "dms")  # decimal degrees, degrees and decimal minutes, d-m-s
LEGEND_SIZE = 2.4  # mm; smaller on small margins or long lines, so everything fits
TITLE_FILL = 0.7  # the title's letters, as a share of the height of its band
CAP_HEIGHT = 0.7  # of a capital, in em: what centres the title (DejaVu 0.73, Garamond 0.65)


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


def _to_page(
    geom: BaseGeometry, tr: Transformer, frame: Frame, pad: float = 0.0
) -> BaseGeometry | None:
    """The geometry in page mm, cut at the map box (`pad` mm past it, if given)."""

    def project(coords: np.ndarray) -> np.ndarray:
        x, y = tr.transform(coords[:, 0], coords[:, 1])
        return np.column_stack((x, y))

    geom = affine_transform(shapely.transform(geom, project), frame.page_matrix())
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    x0, y0 = frame.map_x - pad, frame.map_y - pad
    clipped = shapely.clip_by_rect(
        geom, x0, y0, x0 + frame.map_w + 2 * pad, y0 + frame.map_h + 2 * pad
    )
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
    """A tile in mm, repeated over the fill: parallel lines (dashed or not), dots or
    crosses ("+", `size` mm across; with `stagger`, every other row moved half a step)."""
    s = float(p["spacing"])
    h = s
    colour = quoteattr(str(p.get("color", "#000000")))
    if p["kind"] == "crosses":
        w = s
        a = float(p.get("size", s / 3)) / 2
        centres = [(s / 2, s / 2)]
        if p.get("stagger"):
            h = 2 * s
            centres += [(0, 1.5 * s), (s, 1.5 * s)]
        d = "".join(
            f"M{_num(x - a)} {_num(y)}h{_num(2 * a)}M{_num(x)} {_num(y - a)}v{_num(2 * a)}"
            for x, y in centres
        )
        mark = f'<path d="{d}" fill="none" stroke={colour} stroke-width="{p.get("width", 0.1)}"/>'
    elif p["kind"] == "lines":
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
        f'<rect width="{_num(w)}" height="{_num(h)}" fill={quoteattr(str(background))}/>'
        if background
        else ""
    )
    angle = float(p.get("angle", 0))
    rotate = f' patternTransform="rotate({angle:g})"' if angle else ""
    return (
        f'<pattern id="{pid}" patternUnits="userSpaceOnUse" width="{_num(w)}" '
        f'height="{_num(h)}"{rotate}>{rect}{mark}</pattern>'
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
    styles = {c: job.theme.style(layer.name, c) for c in layer.classes}
    # Shore lines run inside the edge of the water: cut it a bit past the map, so the
    # edge of the map is not a shore (the zone's clip hides what is past it).
    pad = max((max(s.get("shore-lines") or [0]) for s in styles.values()), default=0)
    pad = pad + 1 if pad else 0.0
    by_class: dict[str, list[BaseGeometry]] = {c: [] for c in layer.classes}
    for item in job.features.get(layer.name, []):
        page_geom = _to_page(item.geom, tr, job.frame, pad)
        if page_geom is not None:
            by_class[item.cls].append(page_geom)
    for cls, style in styles.items():
        if style.get("join"):
            _join(cls, style["join"], by_class, styles)
    casings, out = [], []
    for cls in layer.classes:
        d = path_data(by_class[cls])
        if not d:
            continue
        style = _with_patterns(styles[cls], job.label)
        style.pop("join", None)
        shore = _shore(style, by_class[cls], job.frame)
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
        if shore:
            out.append(
                f'<path id="{job.label}-{layer.name}-{cls}-shore" class="{cls} shore" '
                f'{_attrs(shore[0])} d="{shore[1]}"/>'
            )
    # Every casing under every line: where two streets meet, their outlines do not cut them.
    return casings + out


def _join(
    cls: str,
    lines: list[str],
    by_class: dict[str, list[BaseGeometry]],
    styles: dict[str, dict[str, str | float]],
) -> None:
    """The `lines` classes become part of the `cls` area, as wide as they are drawn.

    A river then flows into its lake as one body of water, with one edge, instead of
    a thick line drawn over the lake (Nov 4). The other classes of the layer (the
    streams) stop at the edge of that body. Changes `by_class` in place.
    """
    parts = [p for g in by_class[cls] for p in _parts(g)]
    body = [p for p in parts if p.geom_type == "Polygon"]
    for line in lines:
        s = styles[line]
        half = float(s.get("stroke-width", 0)) / 2 + float(s.get("casing-width", 0))
        body += [shapely.buffer(g, half, quad_segs=4) for g in by_class[line]]
        by_class[line] = []
    merged = shapely.union_all(body)
    by_class[cls] = [merged] + [p for p in parts if p.geom_type != "Polygon"]
    for other in by_class:
        if other != cls and by_class[other]:
            cut = (shapely.difference(g, merged) for g in by_class[other])
            by_class[other] = [g for g in cut if not g.is_empty]


def _shore(
    style: dict[str, str | float], geoms: list[BaseGeometry], frame: Frame
) -> tuple[dict[str, str | float], str] | None:
    """Lines along the shore, `shore-lines` mm inside it, as on old engraved maps.

    Takes the shore keys out of `style`, which are not SVG attributes. Returns the
    lines' style and path data, or None if there are none.
    """
    distances = style.pop("shore-lines", None)
    colour = style.pop("shore-color", style.get("stroke", "#000000"))
    width = style.pop("shore-width", 0.08)
    areas = [p for g in geoms for p in _parts(g) if p.geom_type == "Polygon"]
    if not distances or not areas:
        return None
    water = shapely.union_all(areas)
    x0, y0, x1, y1 = frame.map_x, frame.map_y, frame.map_x + frame.map_w, frame.map_y + frame.map_h
    lines = [
        shapely.clip_by_rect(shapely.buffer(water, -float(d), quad_segs=4).boundary, x0, y0, x1, y1)
        for d in distances
    ]
    d = path_data([g for g in lines if not g.is_empty])
    if not d:
        return None
    return {"fill": "none", "stroke": colour, "stroke-width": width, "stroke-linejoin": "round"}, d


def _casing(style: dict[str, str | float]) -> dict[str, str | float] | None:
    """The outline under a line: the same line, `casing-width` mm wider on each side.

    Takes the casing keys out of `style`, which are not SVG attributes. With
    `casing-opacity` the outline is see-through (a band of colour along a boundary,
    Nov 4) while the line over it stays solid.
    """
    width = style.pop("casing-width", None)
    colour = style.pop("casing-color", None)
    see_through = style.pop("casing-opacity", None)
    if not width or not colour:
        return None
    casing = {
        k: v for k, v in style.items() if k in ("stroke-linecap", "stroke-linejoin", "opacity")
    }
    if see_through is not None:
        casing["stroke-opacity"] = see_through
    return {
        "fill": "none",
        "stroke": colour,
        "stroke-width": _num(float(style.get("stroke-width", 0)) + 2 * float(width)),
        **casing,
    }


def _hillshade_layer(job: Job, layer: Layer) -> list[str]:
    """The relief from the map's DEM, whose grid is aligned with the map rectangle: a
    shaded PNG over it (`style = "shade"`, the default) or, with `style = "hatch"`, lines
    over the slopes, one set per band of the theme's `bands`."""
    style = dict(job.theme.style(layer.name, "shade"))
    kind = style.pop("style", "shade")
    bands = style.pop("bands", [])
    shadow = str(style.pop("shadow", "#000000"))
    highlight = str(style.pop("highlight", "#ffffff"))
    f = job.frame
    out = []
    for item in job.features.get(layer.name, []):
        if item.raster is None:
            continue
        if kind == "hatch":
            out += _hatches(job, layer, item.raster, bands, style)
            continue
        shade = relief.hillshade(item.raster)
        png = base64.b64encode(relief.shade_png(shade, shadow, highlight)).decode()
        out.append(
            f'<image id="{job.label}-{layer.name}-shade" class="shade" {_attrs(style)} '
            f'x="{_num(f.map_x)}" y="{_num(f.map_y)}" width="{_num(f.map_w)}" '
            f'height="{_num(f.map_h)}" preserveAspectRatio="none" '
            f'xlink:href="data:image/png;base64,{png}"/>'
        )
    return out


def _hatches(job: Job, layer: Layer, dem: Path, bands: list[dict], style: dict) -> list[str]:
    """One path per band: lines where the ground is steeper than the band's `slope`."""
    f = job.frame
    grid = relief.read_grid(relief.slope(dem))
    area = (f.map_x, f.map_y, f.map_w, f.map_h)
    out = []
    for n, band in enumerate(bands, 1):
        d = relief.hatch(
            grid,
            area,
            float(band["slope"]),
            float(band["spacing"]),
            float(band.get("angle", 0)),
            float(band.get("offset", 0)),
        )
        if not d:
            continue
        stroke = {
            "fill": "none",
            "stroke": band.get("color", job.theme.page["ink"]),
            "stroke-width": band.get("width", 0.1),
            "stroke-linecap": "butt",
        }
        out.append(
            f'<path id="{job.label}-{layer.name}-band-{n}" class="shade" '
            f'{_attrs(stroke | style)} d="{d}"/>'
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


# A place's name that is taken tries these spots, in steps of its box's height (halo
# included) and POINT_GAP em more, from its point: on it, then just over it, then just
# under it. Further, it would no longer point at its place. The gap clears a bigger
# name beside it (a hamlet's, next to a neighbourhood's).
POINT_SHIFTS = (0.0, -1.0, 1.0)
POINT_GAP = 0.3
LINE_HALF_HEIGHT = 0.6  # em each side of the line a textPath name takes (dy = 0.35 em)

Labels = dict[tuple[str, str], list[str]]  # (layer, class) -> its <text> elements


def _halo(style: dict) -> float:
    return float(style.get("stroke-width", 0)) / 2


def _point_label(xy, text: str, style: dict, whole, placer: Placer) -> str | None:
    """A place's name at its point, or a little over or under it if that is taken."""
    bounds = _place_box(0, 0, text, style).bounds
    step = bounds[3] - bounds[1] + POINT_GAP * float(style["font-size"])
    for shift in POINT_SHIFTS:
        x, y = xy[0], xy[1] + shift * step
        b = _place_box(x, y, text, style)
        if b.within(whole) and placer.take(b):
            return f'<text x="{_num(x)}" y="{_num(y)}">{escape(text)}</text>'
    return None


def _area_label(geom: BaseGeometry, text: str, style: dict, whole, placer: Placer) -> str | None:
    """A lake's or a park's name, centred where its biggest part on the map is widest
    (its pole of inaccessibility), and only if it fits inside it (half a letter over
    the shore at most)."""
    size = float(style["font-size"])
    parts = [p for p in _parts(geom.intersection(whole)) if p.geom_type == "Polygon"]
    if not parts:
        return None
    part = max(parts, key=lambda p: p.area)
    centre = polylabel(part, tolerance=size / 4)
    x, y = centre.x, centre.y + 0.275 * size  # the baseline, for the box to sit on the centre
    b = _place_box(x, y, text, style)
    if b.within(whole) and part.buffer(size / 2).contains(b) and placer.take(b):
        return f'<text x="{_num(x)}" y="{_num(y)}">{escape(text)}</text>'
    return None


def _place_labels(job: Job, tr: Transformer, north: bool = True) -> tuple[list[str], Labels]:
    """Every name of the zone, placed most important first (`LABEL_PRIORITY`) so that
    none overlaps another or the north arrow: one that finds its place taken tries the
    others it has (`POINT_SHIFTS`, a line's `street_slots`) and, if none is free, is
    left out. Gives the <path>s the names along lines are written on, and the names.

    No letter goes past the edge of the map: a place name that does not fit is left
    out, and a name along a line is only written on the stretch that is half a letter
    and the halo away from the edge.
    """
    f = job.frame
    whole = _map_area(f)
    placer = Placer([_north_box(f)] if north else [])
    present = {layer.name for layer in job.layers if layer.text}
    defs: list[str] = []
    labels: Labels = {}
    for name, cls in LABEL_PRIORITY:
        if name not in present:
            continue
        style = job.theme.style(name, cls)
        size = float(style["font-size"])
        inner = _map_area(f, size / 2 + _halo(style))
        items = [i for i in job.features.get(name, []) if i.cls == cls and i.text]
        texts: list[str] = []
        lines: dict[str, list[LineString]] = {}
        for item in sorted(items, key=lambda i: i.rank):  # stable: OSM's order in a rank
            kind = item.geom.geom_type
            text = None
            if kind == "Point":
                xy = _page_xy(item.geom, tr, f)
                if xy is not None:
                    text = _point_label(xy, item.text, style, whole, placer)
            elif kind in ("Polygon", "MultiPolygon"):
                page = _to_page(item.geom, tr, f)
                if page is not None:
                    text = _area_label(page, item.text, style, whole, placer)
            else:
                page = _to_page(item.geom, tr, f)
                if page is not None:
                    lines.setdefault(item.text, []).extend(
                        p
                        for p in _parts(page.intersection(inner))
                        if p.geom_type == "LineString" and not p.is_empty
                    )
                continue
            if text:
                texts.append(text)
        n = 0
        room = (LINE_HALF_HEIGHT * size + _halo(style)) if lines else 0
        for text, parts in sorted(lines.items()):
            for pieces in street_slots(parts, text, size) if parts else []:
                taken = (p for p in pieces if placer.take(p.buffer(room, cap_style="flat")))
                piece = next(taken, None)
                if piece is None:
                    continue
                n += 1
                pid = f"{job.label}-{name}-{cls}-{n}"
                defs.append(f'<path id="{pid}" d="M{_coords(piece.coords)}"/>')
                texts.append(
                    f'<text dy="0.35em"><textPath xlink:href="#{pid}" startOffset="50%" '
                    f'text-anchor="middle">{escape(text)}</textPath></text>'
                )
        labels[(name, cls)] = texts
    return defs, labels


def _text_layer(job: Job, layer: Layer, labels: Labels) -> list[str]:
    """A label layer: a group per class, bottom to top, with the names that were placed."""
    groups = []
    for cls in layer.classes:
        texts = labels.get((layer.name, cls))
        if texts:
            style = job.theme.style(layer.name, cls)
            groups.append(
                f'<g id="{job.label}-{layer.name}-{cls}" class="{cls}" {_attrs(style)}>'
                + "".join(texts)
                + "</g>"
            )
    return groups


def _job_group(job: Job, north: bool = True) -> str:
    tr = Transformer.from_crs(4326, job.frame.crs, always_xy=True)
    label = f"{job.label.upper()} 1:{job.frame.scale} {job.theme.name}"
    opacity = f' opacity="{job.opacity:g}"' if job.opacity < 1 else ""
    f = job.frame
    # Every zone is clipped to the map: the geometry is cut at the edge, but a round
    # line end, a casing or a stroke along the edge would still reach past it by half a width.
    if f.shape == "circle":
        shape = f'<circle cx="{_num(f.map_cx)}" cy="{_num(f.map_cy)}" r="{_num(f.map_w / 2)}"/>'
    else:
        shape = (
            f'<rect x="{_num(f.map_x)}" y="{_num(f.map_y)}" '
            f'width="{_num(f.map_w)}" height="{_num(f.map_h)}"/>'
        )
    paths, labels = _place_labels(job, tr, north)
    out = [
        f'<g id="area-{job.label}" inkscape:groupmode="layer" '
        f'inkscape:label={quoteattr(label)}{opacity} clip-path="url(#clip-{job.label})">',
        f'<defs><clipPath id="clip-{job.label}">{shape}</clipPath>{_pattern_defs(job)}'
        f"{''.join(paths)}</defs>",
    ]
    for layer in job.layers:
        out.append(
            f'<g id="{job.label}-{layer.name}" inkscape:groupmode="layer" '
            f'inkscape:label="{layer.name}">'
        )
        if layer.text:
            out += _text_layer(job, layer, labels)
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
    """The bottom lines of the legend: one, shrunk by `_legend` if it is too long.

    Both: the corners, the scales and the attribution (ODbL asks for it on every map).
    Full also gives the paper, before the attribution, and writes that one in full.
    With relief, a second line: its credit (ADR 0008).
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
        line = f"{corners} · {scales} · {SHORT_ATTRIBUTION}"
    else:
        line = f"{corners} · {scales} · {f.paper} {f.orientation} · {ATTRIBUTION}"
    # The relief's credit, under it: its licence asks for it, and has no short form.
    return (line, relief.ATTRIBUTION) if uses_relief(jobs) else (line,)


def uses_relief(jobs: list[Job]) -> bool:
    return any(j.features.get(layer.name) for j in jobs for layer in j.layers if layer.dem)


def _legend_size(jobs: list[Job], legend: str, coords: str) -> float:
    """The size of the legend's letters: as big as the margin allows, smaller if its
    longest line would not fit the width."""
    f = jobs[0].frame
    widest = max(len(line) for line in (*legend_lines(jobs, legend, coords), MARK))
    size = min(LEGEND_SIZE, f.margin / 3, f.print_w / (widest * CHAR_WIDTH))
    return math.floor(size * 100) / 100  # down to what `_num` writes, so it still fits


def _legend(jobs: list[Job], ink: str, legend: str, coords: str) -> list[str]:
    """The lines at the bottom and the mark top right, each centred in its margin."""
    f = jobs[0].frame
    lines = legend_lines(jobs, legend, coords)
    size = _legend_size(jobs, legend, coords)
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
        "</g>",
    ]


NORTH_SHARE = 0.045  # the north arrow's height, as a share of the map's short side
NORTH_MAX = 24.0  # mm: on an A0 it would be too big otherwise


def true_north(f: Frame) -> float:
    """Degrees clockwise from the page's up to true north, at the centre of the map.

    The map is drawn on a UTM grid, whose north leans off the meridians the further
    the map is from the zone's central one: half a degree at Cecebre, up to ~2.5.
    """
    back = Transformer.from_crs(f.crs, 4326, always_xy=True)
    ahead = Transformer.from_crs(4326, f.crs, always_xy=True)
    x, y = (f.xmin + f.xmax) / 2, (f.ymin + f.ymax) / 2
    lon, lat = back.transform(x, y)
    nx, ny = ahead.transform(lon, lat + 0.01)
    return math.degrees(math.atan2(nx - x, ny - y))


def _lettering(theme: Theme) -> tuple[str, str]:
    """The theme's lettering (that of its city names; sans-serif if it has none): the
    font family, and the font-style attribute if it has one."""
    font = theme.layers.get("places", {}).get("city", {})  # a partial theme may lack it
    family = font.get("font-family", "sans-serif")
    slant = f' font-style="{font["font-style"]}"' if "font-style" in font else ""
    return family, slant


def _title_layout(f: Frame, title: str) -> tuple[float, float]:
    """(size, baseline) of the title, centred between the top of the paper and the
    bottom of the band (the map, in a rect): its capitals halfway. As big as the band
    allows, smaller if it is too long. Its capitals stay well under the mark, which
    keeps its place in the middle of the top margin."""
    size = min(f.title_band * TITLE_FILL, f.print_w / (len(title) * CHAR_WIDTH))
    band_bottom = f.margin + f.title_band  # the map's top in a rect, above it otherwise
    return size, band_bottom / 2 + CAP_HEIGHT / 2 * size


def _title(f: Frame, theme: Theme, title: str, size: float, baseline: float) -> list[str]:
    """The title, centred on the page, in the theme's lettering and ink."""
    family, slant = _lettering(theme)
    weight = theme.layers.get("places", {}).get("city", {}).get("font-weight")
    bold = f' font-weight="{weight}"' if weight else ""
    return [
        '<g id="title" inkscape:groupmode="layer" inkscape:label="title">',
        f'<text x="{_num(f.page_w / 2)}" y="{_num(baseline)}" text-anchor="middle" '
        f"font-family={quoteattr(family)}{slant}{bold} "
        f'font-size="{_num(size)}" fill="{theme.page["ink"]}">{escape(title)}</text>',
        "</g>",
    ]


def _north_place(f: Frame) -> tuple[float, float, float]:
    """(x, y, h): where the north arrow goes, in the top right corner of the map, and
    its height."""
    h = min(NORTH_MAX, NORTH_SHARE * min(f.map_w, f.map_h))
    half, tip = h * 0.25, -h / 2
    letter_y = tip - h * 0.12  # the N's baseline, just over the tip
    inset = h * 0.5
    x = f.map_x + f.map_w - inset - half
    y = f.map_y + inset - letter_y + h * 0.4 * 0.75  # the top of the N, `inset` under the edge
    return x, y, h


def _north_box(f: Frame) -> BaseGeometry:
    """The room the north arrow and its N take, halo included: no name goes there."""
    x, y, h = _north_place(f)
    return box(x - 0.35 * h, y - h, x + 0.35 * h, y + 0.6 * h)


def _north(f: Frame, theme: Theme) -> str:
    """The north arrow, in the top right corner of the map: half ink, half paper, an N
    over it, all with a halo of paper so it reads over anything. Always drawn. The N
    in the theme's lettering."""
    ink, paper = theme.page["ink"], theme.page["background"]
    family, slant = _lettering(theme)
    x, y, h = _north_place(f)
    half, notch = h * 0.25, h * 0.2  # half the width; how far the base's notch goes in
    tip, base = -h / 2, h / 2
    left = f"M0 {_num(tip)}L{_num(-half)} {_num(base)}L0 {_num(base - notch)}Z"
    right = f"M0 {_num(tip)}L{_num(half)} {_num(base)}L0 {_num(base - notch)}Z"
    size = h * 0.4
    letter_y = tip - h * 0.12  # the N's baseline, just over the tip
    outline = f'fill="none" stroke-linejoin="round" d="{left}{right}"'
    halo = _num(h * 0.1)
    return "\n".join(
        [
            '<g id="north" inkscape:groupmode="layer" inkscape:label="north">',
            f'<g transform="translate({_num(x)} {_num(y)}) rotate({_num(true_north(f))})">',
            f'<path stroke="{paper}" stroke-width="{halo}" {outline}/>',
            f'<path fill="{ink}" d="{left}"/>',
            f'<path fill="{paper}" d="{right}"/>',
            f'<path stroke="{ink}" stroke-width="{_num(h * 0.025)}" {outline}/>',
            f'<text x="0" y="{_num(letter_y)}" text-anchor="middle" font-family={quoteattr(family)}'
            f'{slant} font-weight="bold" font-size="{_num(size)}" fill="{ink}" stroke="{paper}" '
            f'stroke-width="{halo}" stroke-linejoin="round" paint-order="stroke">N</text>',
            "</g>",
            "</g>",
        ]
    )


def _outline(f: Frame, ink: str, width: float | str) -> str:
    if f.shape == "circle":
        return (
            f'<circle cx="{_num(f.map_cx)}" cy="{_num(f.map_cy)}" '
            f'r="{_num(f.map_w / 2)}" fill="none" stroke="{ink}" stroke-width="{width}"/>'
        )
    return (
        f'<rect x="{_num(f.map_x)}" y="{_num(f.map_y)}" width="{_num(f.map_w)}" '
        f'height="{_num(f.map_h)}" fill="none" stroke="{ink}" stroke-width="{width}"/>'
    )


def _paper(f: Frame, page: dict) -> list[str]:
    """The sheet in the page's `background`; with a `margin` colour, the sheet in that
    one and only the map (rectangle, square or circle) in the background."""
    sheet = f'<rect width="{_num(f.page_w)}" height="{_num(f.page_h)}" fill="{{}}"/>'
    if "margin" not in page:
        return [sheet.format(page["background"])]
    fill = page["background"]
    if f.shape == "circle":
        cx, cy, r = _num(f.map_cx), _num(f.map_cy), _num(f.map_w / 2)
        inner = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/>'
    else:
        inner = (
            f'<rect x="{_num(f.map_x)}" y="{_num(f.map_y)}" width="{_num(f.map_w)}" '
            f'height="{_num(f.map_h)}" fill="{fill}"/>'
        )
    return [sheet.format(page["margin"]), inner]


def render(
    jobs: list[Job], legend: str = "full", coords: str = "dd", title: str = "", north: bool = True
) -> str:
    """The SVG of the stacked zones. A `title` goes in the band the frame left for it
    (`fit(..., titled=True)`); without the band it is not drawn. `north=False` leaves
    out the north arrow, and the names may then go where it was."""
    first = jobs[0]
    f = first.frame
    page = first.theme.page
    ink = page["ink"]
    titled = bool(title and f.title_band)
    head = (title,) if titled else ()
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" '
        f'width="{_num(f.page_w)}mm" height="{_num(f.page_h)}mm" '
        f'viewBox="0 0 {_num(f.page_w)} {_num(f.page_h)}">',
        f"<title>{escape(' — '.join(head + legend_lines(jobs, legend, coords) + (MARK,)))}</title>",
        '<g id="page" inkscape:groupmode="layer" inkscape:label="page">',
        *_paper(f, page),
        "</g>",
    ]
    parts += [_job_group(j, north) for j in jobs]
    parts += [
        *([_north(f, first.theme)] if north else []),
        '<g id="frame" inkscape:groupmode="layer" inkscape:label="frame">',
        _outline(f, ink, page["frame-width"]),
        "</g>",
        *(_title(f, first.theme, title, *_title_layout(f, title)) if titled else []),
        *_legend(jobs, ink, legend, coords),
        "</svg>",
    ]
    return "\n".join(parts) + "\n"

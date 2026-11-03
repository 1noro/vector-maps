"""From two WGS84 corners to a map frame on paper.

The user gives the top-left and the bottom-right corner. The area is turned into
a rectangle in a local UTM projection (metres, so the scale is true), and then
grown (never cropped) until it has the exact shape of the printable part of the
paper. That is what lets two areas with different zoom share the same page.
"""

from dataclasses import dataclass

from pyproj import CRS, Transformer

from vectormaps.paper import ORIENTATIONS, paper_size

MIN_MARGIN_MM = 6.0  # the attribution line lives in the margin


@dataclass(frozen=True)
class Frame:
    """A map rectangle placed on a page. Lengths in mm on paper, metres on the ground."""

    paper: str
    orientation: str
    page_w: float
    page_h: float
    margin: float
    crs: CRS
    xmin: float
    ymin: float
    xmax: float
    ymax: float
    growth: float  # how much the requested area grew to fit the paper (0.25 = +25% area)

    @property
    def map_w(self) -> float:
        return self.page_w - 2 * self.margin

    @property
    def map_h(self) -> float:
        return self.page_h - 2 * self.margin

    @property
    def metres_per_mm(self) -> float:
        return (self.xmax - self.xmin) / self.map_w

    @property
    def scale(self) -> int:
        """The N of a 1:N scale."""
        return round(self.metres_per_mm * 1000)

    def lonlat_bounds(self, pad: float = 0.02) -> tuple[float, float, float, float]:
        """(south, west, north, east) covering the frame, with a small relative padding."""
        back = Transformer.from_crs(self.crs, 4326, always_xy=True)
        corners = [
            back.transform(x, y) for x in (self.xmin, self.xmax) for y in (self.ymin, self.ymax)
        ]
        lons = [c[0] for c in corners]
        lats = [c[1] for c in corners]
        dlon = (max(lons) - min(lons)) * pad
        dlat = (max(lats) - min(lats)) * pad
        return min(lats) - dlat, min(lons) - dlon, max(lats) + dlat, max(lons) + dlon

    def corners(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """((lat, lon) top-left, (lat, lon) bottom-right) of the map as it is on the paper."""
        back = Transformer.from_crs(self.crs, 4326, always_xy=True)
        (lon1, lat1) = back.transform(self.xmin, self.ymax)
        (lon2, lat2) = back.transform(self.xmax, self.ymin)
        return (lat1, lon1), (lat2, lon2)

    def page_matrix(self) -> list[float]:
        """Affine matrix [a, b, d, e, xoff, yoff] taking projected metres to page mm."""
        s = 1.0 / self.metres_per_mm
        return [s, 0.0, 0.0, -s, self.margin - self.xmin * s, self.margin + self.ymax * s]


def parse_corner(text: str) -> tuple[float, float]:
    """Parse 'LAT,LON' into (lat, lon), validating ranges."""
    try:
        lat_s, lon_s = text.split(",")
        lat, lon = float(lat_s), float(lon_s)
    except ValueError:
        raise ValueError(f"corner must look like LAT,LON (got {text!r})") from None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"corner out of range: {text!r}")
    return lat, lon


def utm_crs(lon: float, lat: float) -> CRS:
    zone = min(60, max(1, int((lon + 180) // 6) + 1))
    return CRS.from_epsg((32600 if lat >= 0 else 32700) + zone)


def fit(
    top_left: tuple[float, float],
    bottom_right: tuple[float, float],
    paper: str,
    margin: float = 10.0,
    orientation: str = "auto",
) -> Frame:
    """Fit the area between two (lat, lon) corners to a paper size."""
    (lat1, lon1), (lat2, lon2) = top_left, bottom_right
    if lat1 <= lat2:
        raise ValueError("top-left must be north of bottom-right (its latitude must be larger)")
    if lon1 >= lon2:
        raise ValueError("top-left must be west of bottom-right (its longitude must be smaller)")
    if margin < MIN_MARGIN_MM:
        raise ValueError(f"margin must be at least {MIN_MARGIN_MM:g} mm (room for the attribution)")
    if orientation != "auto" and orientation not in ORIENTATIONS:
        raise ValueError(f"orientation must be auto, landscape or portrait, not {orientation!r}")

    crs = utm_crs((lon1 + lon2) / 2, (lat1 + lat2) / 2)
    fwd = Transformer.from_crs(4326, crs, always_xy=True)
    pts = [fwd.transform(lon, lat) for lat in (lat1, lat2) for lon in (lon1, lon2)]
    xmin = min(p[0] for p in pts)
    xmax = max(p[0] for p in pts)
    ymin = min(p[1] for p in pts)
    ymax = max(p[1] for p in pts)
    w, h = xmax - xmin, ymax - ymin

    if orientation == "auto":
        orientation = "landscape" if w >= h else "portrait"
    page_w, page_h = paper_size(paper, orientation)
    if page_w - 2 * margin <= 0 or page_h - 2 * margin <= 0:
        raise ValueError("margin leaves no room for the map")
    target = (page_w - 2 * margin) / (page_h - 2 * margin)

    if w / h < target:  # too narrow for the paper: widen
        new_w, new_h = h * target, h
    else:  # too wide: heighten
        new_w, new_h = w, w / target
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    return Frame(
        paper=paper.upper(),
        orientation=orientation,
        page_w=page_w,
        page_h=page_h,
        margin=margin,
        crs=crs,
        xmin=cx - new_w / 2,
        xmax=cx + new_w / 2,
        ymin=cy - new_h / 2,
        ymax=cy + new_h / 2,
        growth=(new_w * new_h) / (w * h) - 1,
    )

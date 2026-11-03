"""The layers: what OSM tags go into each one, and how to ask Overpass for them.

A layer has rules; each rule gives a class (the unit a theme styles) to the
features whose tags match. A rule applies to polygons or to lines, which is
decided by the geometry that `osmium export` builds, not by us.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Tag:
    key: str
    values: tuple[str, ...] | None = None  # None: any value
    exclude: tuple[str, ...] = ()

    def matches(self, tags: dict[str, str]) -> bool:
        v = tags.get(self.key)
        if v is None or v in self.exclude:
            return False
        return self.values is None or v in self.values

    def overpass(self) -> str:
        sel = f'["{self.key}"]'
        if self.values is not None:
            sel = f'["{self.key}"~"^({"|".join(self.values)})$"]'
        if self.exclude:
            sel += f'["{self.key}"!~"^({"|".join(self.exclude)})$"]'
        return sel


@dataclass(frozen=True)
class Rule:
    cls: str
    geometry: str  # "polygon", "line" or "point"
    tag: Tag
    also: tuple[Tag, ...] = ()  # more tags that must be there (e.g. a name, for labels)

    def matches(self, tags: dict[str, str]) -> bool:
        return self.tag.matches(tags) and all(t.matches(tags) for t in self.also)

    def overpass(self) -> str:
        return self.tag.overpass() + "".join(t.overpass() for t in self.also)


@dataclass(frozen=True)
class Layer:
    name: str
    rules: tuple[Rule, ...]  # first match wins; draw order is `classes`
    classes: tuple[str, ...]  # bottom to top
    text: bool = False  # a label layer: its features are drawn as text, not as shapes

    def classify(self, geometry: str, tags: dict[str, str]) -> str | None:
        for rule in self.rules:
            if rule.geometry == geometry and rule.matches(tags):
                return rule.cls
        return None

    def overpass_query(self, bounds: tuple[float, float, float, float], timeout: int = 180) -> str:
        """Overpass QL for this layer inside (south, west, north, east)."""
        s, w, n, e = (f"{v:.5f}" for v in bounds)
        box = f"({s},{w},{n},{e})"
        lines: list[str] = []
        for rule in self.rules:
            sel = rule.overpass()
            if rule.geometry == "point":
                lines.append(f"  node{sel}{box};")
                continue
            lines.append(f"  way{sel}{box};")
            if rule.geometry == "polygon":
                lines.append(f'  relation["type"="multipolygon"]{sel}{box};')
        body = "\n".join(dict.fromkeys(lines))  # dedupe, keep order
        return f"[out:xml][timeout:{timeout}];\n(\n{body}\n);\n(._;>;);\nout meta;\n"


NAMED = (Tag("name"),)


def _rules(
    cls: str,
    geometry: str,
    key: str,
    *values: str,
    exclude: tuple[str, ...] = (),
    also: tuple[Tag, ...] = (),
):
    return Rule(cls, geometry, Tag(key, values or None, exclude), also)


LAYERS: dict[str, Layer] = {
    layer.name: layer
    for layer in (
        Layer(
            "water",
            (
                _rules("water", "polygon", "natural", "water", "bay"),
                _rules("water", "polygon", "waterway", "riverbank", "dock"),
                _rules("water", "polygon", "landuse", "reservoir", "basin"),
                _rules("river", "line", "waterway", "river"),
                _rules("canal", "line", "waterway", "canal"),
                _rules("stream", "line", "waterway", "stream", "ditch", "drain"),
            ),
            ("water", "stream", "canal", "river"),
        ),
        Layer(
            "green",
            (
                _rules("green", "polygon", "leisure", "park", "garden", "nature_reserve"),
                _rules(
                    "green",
                    "polygon",
                    "landuse",
                    "grass",
                    "forest",
                    "meadow",
                    "village_green",
                    "recreation_ground",
                ),
                _rules("green", "polygon", "natural", "wood", "scrub", "grassland", "heath"),
            ),
            ("green",),
        ),
        Layer(
            "buildings",
            (_rules("building", "polygon", "building", exclude=("no",)),),
            ("building",),
        ),
        Layer(
            "roads",
            (
                _rules(
                    "major",
                    "line",
                    "highway",
                    "motorway",
                    "motorway_link",
                    "trunk",
                    "trunk_link",
                    "primary",
                    "primary_link",
                ),
                _rules(
                    "secondary",
                    "line",
                    "highway",
                    "secondary",
                    "secondary_link",
                    "tertiary",
                    "tertiary_link",
                ),
                _rules(
                    "minor",
                    "line",
                    "highway",
                    "residential",
                    "unclassified",
                    "living_street",
                    "road",
                ),
                _rules("service", "line", "highway", "service"),
                _rules(
                    "path",
                    "line",
                    "highway",
                    "pedestrian",
                    "footway",
                    "cycleway",
                    "path",
                    "steps",
                    "track",
                ),
            ),
            ("path", "service", "minor", "secondary", "major"),
        ),
        Layer(
            "railways",
            (
                _rules("rail", "line", "railway", "rail", "light_rail", "narrow_gauge"),
                _rules("tram", "line", "railway", "tram"),
            ),
            ("tram", "rail"),
        ),
        Layer(
            "street-names",
            (
                _rules("major", "line", "highway", "motorway", "trunk", "primary", also=NAMED),
                _rules("secondary", "line", "highway", "secondary", "tertiary", also=NAMED),
                _rules(
                    "minor",
                    "line",
                    "highway",
                    "residential",
                    "unclassified",
                    "living_street",
                    also=NAMED,
                ),
            ),
            ("minor", "secondary", "major"),
            text=True,
        ),
        Layer(
            "places",
            (
                _rules("city", "point", "place", "city", also=NAMED),
                _rules("town", "point", "place", "town", also=NAMED),
                _rules("village", "point", "place", "village", also=NAMED),
                _rules(
                    "suburb",
                    "point",
                    "place",
                    "suburb",
                    "quarter",
                    "neighbourhood",
                    "hamlet",
                    also=NAMED,
                ),
            ),
            ("suburb", "village", "town", "city"),
            text=True,
        ),
    )
}

# Bottom to top; the labels go over everything.
DEFAULT_ORDER = ("water", "green", "buildings", "railways", "roads", "street-names", "places")


def select(names: list[str] | None) -> list[Layer]:
    """Layers by name, always returned in drawing order (bottom to top)."""
    if not names:
        names = list(DEFAULT_ORDER)
    unknown = [n for n in names if n not in LAYERS]
    if unknown:
        raise ValueError(f"unknown layer(s) {', '.join(unknown)}; use {', '.join(LAYERS)}")
    return [LAYERS[n] for n in DEFAULT_ORDER if n in names]

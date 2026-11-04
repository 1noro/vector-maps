"""The layers: what OSM tags go into each one, and how to ask Overpass for them.

A layer has rules; each rule gives a class (the unit a theme styles) to the
features whose tags match. A rule applies to polygons or to lines, which is
decided by the geometry that `osmium export` builds, not by us.
"""

from dataclasses import dataclass

from vectormaps.boundaries import LEVELS


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
    dem: bool = False  # relief: from the elevation model (relief.py), not from OSM
    # Administrative boundaries (boundaries.py): admin_level -> class, instead of rules.
    admin: tuple[tuple[int, str], ...] = ()

    def classify(self, geometry: str, tags: dict[str, str]) -> str | None:
        for rule in self.rules:
            if rule.geometry == geometry and rule.matches(tags):
                return rule.cls
        return None

    def overpass_query(self, bounds: tuple[float, float, float, float], timeout: int = 180) -> str:
        """Overpass QL for this layer inside (south, west, north, east)."""
        s, w, n, e = (f"{v:.5f}" for v in bounds)
        box = f"({s},{w},{n},{e})"
        if self.admin:
            return _boundary_query(box, timeout)
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


def _boundary_query(box: str, timeout: int) -> str:
    """The boundary relations that touch the box, but only their ways inside it (with
    their nodes): the relation itself goes without geometry. The same query for every
    boundary layer, all levels, so the second and third come from the cache."""
    levels = "|".join(str(n) for n in LEVELS)
    return (
        f"[out:xml][timeout:{timeout}];\n"
        f'rel["boundary"="administrative"]["admin_level"~"^({levels})$"]{box}->.r;\n'
        f"way(r.r){box}->.w;\n"
        "(.r;.w;node(w.w););\n"
        "out meta;\n"
    )


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
        # Administrative boundaries (ADR 0010), from the most local up; each layer
        # draws a shared edge only if no higher layer on the map does.
        Layer("parishes", (), ("parish",), admin=((9, "parish"), (10, "parish"))),
        Layer("municipalities", (), ("municipality",), admin=((8, "municipality"),)),
        Layer(
            "boundaries",
            (),
            ("district", "province", "region", "country"),
            admin=(
                (2, "country"),
                (3, "region"),
                (4, "region"),
                (5, "province"),
                (6, "province"),
                (7, "district"),
            ),
        ),
        # Relief (ADR 0008): no OSM rules, the elevation model gives the shapes.
        Layer("hillshade", (), ("shade",), dem=True),
        Layer("contours", (), ("minor", "major"), dem=True),
    )
}

# Drawing order, bottom to top: water over the ground cover (in OSM woods often overlap
# rivers, Nov 4), the shade over both, the contours under the buildings, the boundaries
# over the roads (a parish edge often runs along one), the labels over everything.
ORDER = (
    "green",
    "water",
    "hillshade",
    "contours",
    "buildings",
    "railways",
    "roads",
    "parishes",
    "municipalities",
    "boundaries",
    "street-names",
    "places",
)
# What a map has when no layers are given: the shapes, without relief, boundaries or names.
DEFAULT = tuple(
    n for n in ORDER if not LAYERS[n].dem and not LAYERS[n].text and not LAYERS[n].admin
)


def _check(names: list[str]) -> None:
    unknown = [n for n in names if n not in LAYERS]
    if unknown:
        raise ValueError(f"unknown layer(s) {', '.join(unknown)}; use {', '.join(ORDER)}")


def select(
    names: list[str] | None,
    exclude: list[str] | None = None,
    include: list[str] | None = None,
) -> list[Layer]:
    """Layers by name (the default set if none), plus `include`, minus `exclude`.

    Always in drawing order (bottom to top).
    """
    names = list(names or DEFAULT)
    exclude = exclude or []
    include = include or []
    _check(names + include + exclude)
    both = [n for n in include if n in exclude]
    if both:
        raise ValueError(f"{', '.join(both)}: both included and excluded; pick one")
    chosen = [LAYERS[n] for n in ORDER if (n in names or n in include) and n not in exclude]
    if not chosen:
        raise ValueError("no layers left to draw; check --layers and --exclude-layers")
    return chosen

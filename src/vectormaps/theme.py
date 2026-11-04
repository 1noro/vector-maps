"""Themes: TOML files that say how each layer class looks.

A theme may also define fill patterns (hatching, dots) under `[patterns.<name>]`;
a style uses one as `fill = "pattern:<name>"`, and the SVG gets a `<pattern>` for it.
The hillshade is a shaded picture or, with `style = "hatch"`, lines over the slopes.
An area class can take in line classes of its layer (`join`, rivers into lakes) and
have lines along its shore (`shore-lines`).
"""

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

THEMES_DIR = Path(__file__).parent / "themes"
PATTERN_KINDS = ("lines", "dots", "crosses")
PATTERN_PREFIX = "pattern:"
RELIEF_STYLES = ("shade", "hatch")  # the hillshade: a shaded picture, or lines on the slopes


@dataclass(frozen=True)
class Theme:
    name: str
    page: dict[str, str | float]
    layers: dict[str, dict[str, dict[str, str | float]]]
    patterns: dict[str, dict[str, str | float]] = field(default_factory=dict)

    def style(self, layer: str, cls: str) -> dict[str, str | float]:
        try:
            return self.layers[layer][cls]
        except KeyError:
            raise ValueError(f"theme {self.name!r} has no style for {layer}.{cls}") from None


# Themes made from another by tinting it: black becomes the tint, white stays white.
TINTED = {"monochrome": "bw"}
DEFAULT_TINT = "#1f3b5c"  # a dark blue that still prints well
_HEX = re.compile(r"#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})")


def parse_tint(text: str) -> tuple[int, int, int]:
    m = _HEX.fullmatch(text.strip())
    if not m:
        raise ValueError(f"tint must be a hex colour like #1f3b5c or 1f3b5c, not {text!r}")
    digits = m.group(1)
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    r, g, b = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
    return r, g, b


def _tint_colour(value: str, tint: tuple[int, int, int]) -> str:
    """A grey (or any colour, by its lightness) as the same lightness of the tint."""
    r, g, b = parse_tint(value)
    light = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    return "#" + "".join(f"{round(t + (255 - t) * light):02x}" for t in tint)


def tinted(theme: Theme, tint: str, name: str) -> Theme:
    rgb = parse_tint(tint)

    def tint(v):
        if isinstance(v, str) and v.startswith("#"):
            return _tint_colour(v, rgb)
        if isinstance(v, list):  # the hillshade's hatch bands
            return [recolour(x) if isinstance(x, dict) else x for x in v]
        return v

    def recolour(style: dict) -> dict:
        return {k: tint(v) for k, v in style.items()}

    layers = {
        layer: {cls: recolour(style) for cls, style in classes.items()}
        for layer, classes in theme.layers.items()
    }
    patterns = {n: recolour(p) for n, p in theme.patterns.items()}
    return Theme(name, recolour(theme.page), layers, patterns)


def _check_patterns(name: str, layers: dict, patterns: dict) -> None:
    """Every pattern has a known kind and every `pattern:` a style names exists."""
    for pname, p in patterns.items():
        if p.get("kind") not in PATTERN_KINDS:
            raise ValueError(
                f"theme {name!r}: pattern {pname!r} needs kind = one of {', '.join(PATTERN_KINDS)}"
            )
        if not float(p.get("spacing", 0)) > 0:
            raise ValueError(f"theme {name!r}: pattern {pname!r} needs a spacing above 0 (mm)")
    for layer, classes in layers.items():
        for cls, style in classes.items():
            for value in style.values():
                if not (isinstance(value, str) and value.startswith(PATTERN_PREFIX)):
                    continue
                pname = value.removeprefix(PATTERN_PREFIX)
                if pname not in patterns:
                    raise ValueError(
                        f"theme {name!r}: {layer}.{cls} uses {value!r}, "
                        f"but there is no [patterns.{pname}]"
                    )


def _check_relief(name: str, layers: dict) -> None:
    """The hillshade is a shade or a hatch, and a hatch says over which slopes."""
    shade = layers.get("hillshade", {}).get("shade", {})
    kind = shade.get("style", "shade")
    if kind not in RELIEF_STYLES:
        raise ValueError(
            f"theme {name!r}: hillshade.shade style is {kind!r}; "
            f"use one of {', '.join(RELIEF_STYLES)}"
        )
    if kind != "hatch":
        return
    bands = shade.get("bands")
    if not (isinstance(bands, list) and bands):
        raise ValueError(
            f"theme {name!r}: a hatched hillshade needs bands = [{{ slope = 6, spacing = 1 }}, …]"
        )
    for band in bands:
        if not (isinstance(band, dict) and "slope" in band and float(band.get("spacing", 0)) > 0):
            raise ValueError(
                f"theme {name!r}: every hillshade band needs a slope (degrees) "
                "and a spacing above 0 (mm)"
            )


def _check_shores(name: str, layers: dict) -> None:
    """`join` names line classes of the same layer; `shore-lines` are distances in mm."""
    for layer, classes in layers.items():
        for cls, style in classes.items():
            joined = style.get("join", [])
            if not isinstance(joined, list) or any(c not in classes or c == cls for c in joined):
                raise ValueError(
                    f"theme {name!r}: {layer}.{cls} join must list classes of {layer} "
                    f"with a style ({', '.join(c for c in classes if c != cls)})"
                )
            shores = style.get("shore-lines", [])
            if not isinstance(shores, list) or not all(
                isinstance(d, int | float) and d > 0 for d in shores
            ):
                raise ValueError(
                    f"theme {name!r}: {layer}.{cls} shore-lines must be distances above 0 (mm), "
                    "like [0.35, 0.8]"
                )


def available() -> list[str]:
    return sorted([p.stem for p in THEMES_DIR.glob("*.toml")] + list(TINTED))


def load(name_or_path: str, tint: str | None = None) -> Theme:
    """A bundled theme by name, or any .toml file by path. `tint` is for `monochrome`."""
    if name_or_path in TINTED:
        return tinted(load(TINTED[name_or_path]), tint or DEFAULT_TINT, name_or_path)
    if tint:
        raise ValueError(f"a tint only goes with the {', '.join(TINTED)} theme")
    path = Path(name_or_path)
    if path.suffix != ".toml":
        path = THEMES_DIR / f"{name_or_path}.toml"
    if not path.is_file():
        raise ValueError(f"unknown theme {name_or_path!r}; bundled: {', '.join(available())}")
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    patterns = data.get("patterns", {})
    _check_patterns(path.stem, data["layers"], patterns)
    _check_relief(path.stem, data["layers"])
    _check_shores(path.stem, data["layers"])
    return Theme(path.stem, data["page"], data["layers"], patterns)

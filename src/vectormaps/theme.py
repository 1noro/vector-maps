"""Themes: TOML files that say how each layer class looks."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

THEMES_DIR = Path(__file__).parent / "themes"


@dataclass(frozen=True)
class Theme:
    name: str
    page: dict[str, str | float]
    layers: dict[str, dict[str, dict[str, str | float]]]

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

    def recolour(style: dict) -> dict:
        return {
            k: _tint_colour(v, rgb) if isinstance(v, str) and v.startswith("#") else v
            for k, v in style.items()
        }

    layers = {
        layer: {cls: recolour(style) for cls, style in classes.items()}
        for layer, classes in theme.layers.items()
    }
    return Theme(name, recolour(theme.page), layers)


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
    return Theme(path.stem, data["page"], data["layers"])

"""Themes: TOML files that say how each layer class looks."""

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


def available() -> list[str]:
    return sorted(p.stem for p in THEMES_DIR.glob("*.toml"))


def load(name_or_path: str) -> Theme:
    """A bundled theme by name, or any .toml file by path."""
    path = Path(name_or_path)
    if path.suffix != ".toml":
        path = THEMES_DIR / f"{name_or_path}.toml"
    if not path.is_file():
        raise ValueError(f"unknown theme {name_or_path!r}; bundled: {', '.join(available())}")
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return Theme(path.stem, data["page"], data["layers"])

"""Names for the map: which name to show (language) and where to put street names."""

import re

from shapely import line_merge
from shapely.geometry import LineString, MultiLineString
from shapely.ops import substring

DEFAULT_LANG = "es"
LOCAL = "local"  # not a language: show the name as mapped, with no translation
_LANG = re.compile(rf"^(?:{LOCAL}|[A-Za-z]{{2,3}}(?:-[A-Za-z0-9]+)*)$")

CHAR_WIDTH = 0.62  # width of a glyph in em; on the high side: a path cuts off what does not fit
LABEL_EVERY = 6  # one street label per this many label-widths of street
MAX_WIGGLE = 1.3  # skip pieces of street that curve more than this (length / chord)


def parse_langs(text: str) -> list[str]:
    """'gl,es' -> ['gl', 'es']: the first language with a name wins."""
    langs = [t.strip() for t in text.split(",") if t.strip()]
    bad = [lang for lang in langs if not _LANG.match(lang)]
    if not langs or bad:
        raise ValueError(
            f"bad language {', '.join(bad) or repr(text)}: use OSM language codes like es, gl, "
            f"en, ja (or {LOCAL}), separated by commas"
        )
    return langs


def pick_name(tags: dict[str, str], langs: list[str]) -> str | None:
    """`name:<lang>` for the first language that has one, else the plain `name`."""
    for lang in langs:
        if lang != LOCAL and tags.get(f"name:{lang}"):
            return tags[f"name:{lang}"]
    return tags.get("name") or None


def text_width(text: str, size: float) -> float:
    return len(text) * size * CHAR_WIDTH


def street_pieces(lines: list[LineString], text: str, size: float) -> list[LineString]:
    """Short stretches of street, oriented to read left to right, to write `text` along.

    The lines of a street (OSM cuts them at every junction) are joined first, so the
    name is repeated per stretch of road and not per way.
    """
    width = text_width(text, size)
    merged = line_merge(MultiLineString(lines)) if len(lines) > 1 else lines[0]
    pieces: list[LineString] = []
    for part in getattr(merged, "geoms", [merged]):
        if part.length < width * 1.25:
            continue
        count = max(1, int(part.length // (width * LABEL_EVERY)))
        for i in range(count):
            centre = part.length * (i + 0.5) / count
            piece = substring(part, centre - width * 0.7, centre + width * 0.7)
            if not isinstance(piece, LineString) or piece.is_empty:
                continue
            (x0, y0), (x1, y1) = piece.coords[0], piece.coords[-1]
            chord = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
            if chord == 0 or piece.length / chord > MAX_WIGGLE:
                continue
            pieces.append(LineString(piece.coords[::-1]) if x1 < x0 else piece)
    return pieces

"""Names for the map: which name to show (language), where a name can go along a line,
and which names fit without overlapping (`Placer`)."""

import math
import re

from shapely import line_merge
from shapely.geometry import LineString, MultiLineString
from shapely.geometry.base import BaseGeometry
from shapely.ops import substring

DEFAULT_LANG = "es"
LOCAL = "local"  # not a language: show the name as mapped, with no translation
_LANG = re.compile(rf"^(?:{LOCAL}|[A-Za-z]{{2,3}}(?:-[A-Za-z0-9]+)*)$")

CHAR_WIDTH = 0.62  # width of a glyph in em; on the high side: a path cuts off what does not fit
LABEL_EVERY = 6  # one street label per this many label-widths of street
MAX_WIGGLE = 1.3  # skip pieces of street that curve more than this (length / chord)
# ...or that bend sharply anywhere: more than MAX_TURN degrees from one step of
# TURN_STEP em along it to the next. On the inside of an elbow the letters pile up
# (Nov 5: "Río Anllóns" on a 58° bend of the river).
MAX_TURN = 30.0
TURN_STEP = 1.0
# Where else a line's label may go when its place is taken: shifted along the line by
# these shares of the room each label has, nearest first (0.5 would reach the next one).
SLOT_SHIFTS = (0.0, 0.15, -0.15, 0.3, -0.3, 0.45, -0.45)


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


def street_slots(lines: list[LineString], text: str, size: float) -> list[list[LineString]]:
    """Where `text` can go along a line (a street, a river), oriented to read left to
    right: one slot per stretch of line, and in each the pieces to try, best first.

    The lines (OSM cuts a street at every junction) are joined first, so the name is
    repeated per stretch of line and not per way: one slot per `LABEL_EVERY` label-widths.
    The first piece of a slot is in its middle; the others, shifted along the line
    (`SLOT_SHIFTS`), are for when that one is taken by another name. A piece shorter
    than the text, or one that curves too much, is no place for it.
    """
    width = text_width(text, size)
    merged = line_merge(MultiLineString(lines)) if len(lines) > 1 else lines[0]
    slots: list[list[LineString]] = []
    for part in getattr(merged, "geoms", [merged]):
        if part.length < width * 1.25:
            continue
        count = max(1, int(part.length // (width * LABEL_EVERY)))
        room = part.length / count
        for i in range(count):
            pieces = []
            for shift in SLOT_SHIFTS:
                piece = _piece(part, room * (i + 0.5 + shift), width, size)
                if piece is not None:
                    pieces.append(piece)
            if pieces:
                slots.append(pieces)
    return slots


def _sharpest_turn(line: LineString, step: float) -> float:
    """The biggest change of direction, in degrees, from one `step` along `line` to the
    next: the line resampled that often, so a wobble shorter than a letter does not count."""
    n = max(2, int(line.length // step))
    pts = [line.interpolate(line.length * i / n).coords[0] for i in range(n + 1)]
    heads = [math.atan2(b[1] - a[1], b[0] - a[0]) for a, b in zip(pts, pts[1:], strict=False)]
    turns = [math.degrees(b - a) for a, b in zip(heads, heads[1:], strict=False)]
    return max((abs((t + 180) % 360 - 180) for t in turns), default=0.0)


def _piece(part: LineString, centre: float, width: float, size: float) -> LineString | None:
    """The stretch of `part` around `centre` to write a text `width` long on, or None."""
    # Kept on the line: shapely reads a negative distance as counted from the end,
    # which gave a sliver at the far end, where only a letter or two showed.
    start = max(0.0, centre - width * 0.7)
    piece = substring(part, start, min(part.length, centre + width * 0.7))
    if not isinstance(piece, LineString) or piece.length < width:
        return None
    (x0, y0), (x1, y1) = piece.coords[0], piece.coords[-1]
    chord = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    if chord == 0 or piece.length / chord > MAX_WIGGLE:
        return None
    if _sharpest_turn(piece, TURN_STEP * size) > MAX_TURN:
        return None
    return LineString(piece.coords[::-1]) if x1 < x0 else piece


def street_pieces(lines: list[LineString], text: str, size: float) -> list[LineString]:
    """The best piece of each slot (`street_slots`): where the name goes if nothing is
    in the way."""
    return [pieces[0] for pieces in street_slots(lines, text, size)]


class Placer:
    """The room the names already take on the page, so the next one does not overlap
    them. Names are offered most important first (`layers.LABEL_PRIORITY`): the first
    to ask for a place keeps it."""

    def __init__(self, taken: list[BaseGeometry] = ()):
        self._taken = list(taken)

    def free(self, shape: BaseGeometry) -> bool:
        x0, y0, x1, y1 = shape.bounds
        for other in self._taken:
            a0, b0, a1, b1 = other.bounds
            # touching is fine (a name just over another); sharing any room is not
            near = a0 < x1 and x0 < a1 and b0 < y1 and y0 < b1
            if near and other.intersection(shape).area > 1e-6:
                return False
        return True

    def take(self, shape: BaseGeometry) -> bool:
        """Keep `shape` for a name if nothing is there yet; say whether it was."""
        if not self.free(shape):
            return False
        self._taken.append(shape)
        return True

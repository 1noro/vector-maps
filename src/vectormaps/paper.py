"""ISO 216 A-series paper sizes, in millimetres (portrait: width x height)."""

PAPERS: dict[str, tuple[float, float]] = {
    "A0": (841.0, 1189.0),
    "A1": (594.0, 841.0),
    "A2": (420.0, 594.0),
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
}

ORIENTATIONS = ("landscape", "portrait")


def paper_size(name: str, orientation: str) -> tuple[float, float]:
    """Return (width, height) in mm for a paper name and a concrete orientation."""
    try:
        w, h = PAPERS[name.upper()]
    except KeyError:
        raise ValueError(f"unknown paper {name!r}; use one of {', '.join(PAPERS)}") from None
    if orientation == "landscape":
        return h, w
    if orientation == "portrait":
        return w, h
    raise ValueError(f"orientation must be 'landscape' or 'portrait', not {orientation!r}")

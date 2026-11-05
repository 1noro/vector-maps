import argparse
import logging
import sys
from pathlib import Path

from vectormaps import geofabrik
from vectormaps import layers as layer_defs
from vectormaps import theme as themes
from vectormaps.area import SHAPES, Frame, corners_around, fit, parse_corner
from vectormaps.download import PBF_DIR, download
from vectormaps.labels import DEFAULT_LANG, parse_langs
from vectormaps.overpass import OverpassError
from vectormaps.paper import PAPERS
from vectormaps.pdf import svg_to_pdf
from vectormaps.pipeline import load_features
from vectormaps.progress import ProgressHandler, Spinner
from vectormaps.render import COORDS, LEGENDS, Job, render
from vectormaps.sources import Bounds, OverpassSource, PbfSource, Source, local_pbf_for
from vectormaps.tmpfile import tmp_beside

log = logging.getLogger("vectormaps")

DEFAULT_PAPER = "A4"
DEFAULT_THEME = "bw"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vectormaps", description="SVG maps from OpenStreetMap, by layers, for print."
    )
    sub = p.add_subparsers(dest="command", required=True)

    m = sub.add_parser(
        "map",
        help="draw an area as SVG, optionally with a second area stacked on top",
        description="Corners and centres are LAT,LON. Use --tl=LAT,LON (with '=') so negative "
        "values parse. The area is either --tl and --br, or --center and --radius.",
    )
    m.add_argument("--tl", metavar="LAT,LON", help="top-left corner")
    m.add_argument("--br", metavar="LAT,LON", help="bottom-right corner")
    m.add_argument("--center", metavar="LAT,LON", help="centre of the area (with --radius)")
    m.add_argument(
        "--radius", type=float, metavar="KM", help="radius in km: the circle is always fully shown"
    )
    m.add_argument("--paper", default=DEFAULT_PAPER, choices=list(PAPERS), type=str.upper)
    m.add_argument("--orientation", default="landscape", choices=["auto", "landscape", "portrait"])
    m.add_argument("--margin", type=float, default=6.0, metavar="MM")
    m.add_argument(
        "--shape",
        default="rect",
        choices=SHAPES,
        help="how the map is printed on the paper: rect fills it, square and circle are centred "
        "and as wide as its short side (circle: clipped, with a thin border). default: %(default)s",
    )
    m.add_argument(
        "--layers", metavar="A,B", help="default: all but relief and names, see `vectormaps list`"
    )
    m.add_argument(
        "--exclude-layers", metavar="A,B", help="layers to leave out of --layers (or the default)"
    )
    m.add_argument(
        "--include-layers",
        metavar="A,B",
        help="layers to add to --layers (or the default), e.g. street-names,places",
    )
    m.add_argument(
        "--lang",
        default=DEFAULT_LANG,
        metavar="CODE[,CODE]",
        help="language of street and place names, by OSM code (es, gl, en, ja…); the first "
        "with a name wins, else the name as mapped. 'local' = as mapped. default: %(default)s",
    )
    m.add_argument(
        "--theme",
        default=DEFAULT_THEME,
        help="bundled theme name or a .toml path. default: %(default)s",
    )
    m.add_argument(
        "--tint",
        metavar="HEX",
        help="colour of the monochrome theme, e.g. #1f3b5c (black becomes it, white stays); "
        f"default: {themes.DEFAULT_TINT}",
    )
    m.add_argument("--out", type=Path, default=Path("out/map.svg"))
    m.add_argument(
        "--pdf",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="also write a PDF of the paper size next to the SVG (default; --no-pdf: only the SVG)",
    )
    m.add_argument(
        "--legend",
        choices=LEGENDS,
        default="minimal",
        help="minimal: only the corners, the scale, a short OSM credit and the mark; full: also "
        "the paper and the full credit. default: %(default)s",
    )
    m.add_argument(
        "--coords",
        choices=COORDS,
        default="dms",
        help="format of the coordinates in the legend: dd 42.88000, -8.54000; "
        "dm 42°52.800'N 8°32.400'W; dms 42°52'48.0\"N 8°32'24.0\"W. default: %(default)s",
    )
    m.add_argument(
        "--title",
        default="",
        help="a title over the map, in a band of its own (the map gets that much shorter)",
    )
    m.add_argument("--cache", type=Path, default=Path("data/cache"))
    m.add_argument("--pbf", type=Path, help="read a local .osm.pbf instead of asking Overpass")
    m.add_argument("--overpass-url", help="default: $OVERPASS_URL or the public server")

    o = m.add_argument_group(
        "overlay",
        "A second area drawn over the first on the same page (same paper, own zoom).",
    )
    o.add_argument("--over-tl", metavar="LAT,LON")
    o.add_argument("--over-br", metavar="LAT,LON")
    o.add_argument("--over-center", metavar="LAT,LON", help="instead of --over-tl/--over-br")
    o.add_argument("--over-radius", type=float, metavar="KM")
    o.add_argument("--over-layers", metavar="A,B", help="default: the ones of the first area")
    o.add_argument("--over-exclude-layers", metavar="A,B", help="leave these out of the overlay")
    o.add_argument("--over-include-layers", metavar="A,B", help="add these to the overlay")
    o.add_argument("--over-theme", help="default: same as --theme")
    o.add_argument("--over-tint", metavar="HEX", help="default: same as --tint")
    o.add_argument("--over-opacity", type=float, default=1.0, metavar="0-1")

    sub.add_parser("list", help="list layers, papers and themes")
    sub.add_parser("wizard", help="the same as `map`, asking for every option in the terminal")

    d = sub.add_parser("download", help="download a .osm.pbf extract (e.g. from Geofabrik)")
    d.add_argument("url")
    d.add_argument("--out-dir", type=Path, default=PBF_DIR)
    return p


def _split(text: str | None) -> list[str] | None:
    return [t.strip() for t in text.split(",") if t.strip()] if text else None


def _describe(label: str, frame: Frame) -> str:
    grown = f", grown {frame.growth:.0%} to fit the paper" if frame.growth > 0.005 else ""
    shape = "" if frame.shape == "rect" else f" {frame.shape}"
    return f"{label}: 1:{frame.scale}, {frame.paper} {frame.orientation}{shape}{grown}"


def offline_hint(areas: list[Bounds], cache: Path) -> str:
    """What to do when Overpass fails and no local extract covers the area."""
    again = "repeat the same `make map` adding"
    with Spinner("looking for an extract of this area on Geofabrik"):
        region = geofabrik.region_for(areas, cache)
    if region is not None:
        return (
            f"hint: work offline with the {region.name} extract, downloaded once:\n"
            f"  make pbf URL={region.url}\n"
            f"  and {again} PBF={PBF_DIR / region.filename}"
        )
    return (
        "hint: work offline with an extract that covers the area, downloaded once\n"
        "  (list: https://download.geofabrik.de/):\n"
        "  make pbf URL=<…-latest.osm.pbf>\n"
        f"  and {again} PBF={PBF_DIR}/<file>.osm.pbf"
    )


def _list() -> int:
    width = max(map(len, layer_defs.ORDER))

    def layers(on: bool) -> None:
        for name in layer_defs.ORDER:
            if (name in layer_defs.DEFAULT) == on:
                classes = ", ".join(layer_defs.LAYERS[name].classes)
                print(f"  {name:<{width}}  {classes}")

    print("layers drawn by default (bottom to top, with their classes):")
    layers(True)
    print()
    print("layers off by default (add them with --include-layers):")
    layers(False)
    print()
    print("papers:", ", ".join(f"{p} (default)" if p == DEFAULT_PAPER else p for p in PAPERS))
    print(
        "themes:",
        ", ".join(f"{t} (default)" if t == DEFAULT_THEME else t for t in themes.available()),
    )
    return 0


def _corners(
    tl: str | None, br: str | None, center: str | None, radius: float | None, flag: str = "--"
) -> tuple[tuple[float, float], tuple[float, float], float | None]:
    """The two corners (and the radius, if any) of an area given as corners or as centre and radius.

    `flag` is the prefix of the option names, only used in the messages.
    """
    if (tl or br) and (center or radius is not None):
        raise ValueError(f"use either {flag}tl and {flag}br, or {flag}center and {flag}radius")
    if center or radius is not None:
        if not (center and radius is not None):
            raise ValueError(f"{flag}center and {flag}radius go together")
        return *corners_around(parse_corner(center), radius), radius
    if not (tl and br):
        raise ValueError(f"give the area: {flag}tl and {flag}br, or {flag}center and {flag}radius")
    return parse_corner(tl), parse_corner(br), None


def _load_jobs(specs: list, source: Source, langs: list[str], cache: Path) -> list[Job]:
    jobs = []
    for label, frame, lyrs, theme, opacity in specs:
        log.info(_describe(label.upper(), frame))
        feats = load_features(frame, lyrs, source, langs, cache)
        jobs.append(Job(label, frame, theme, lyrs, feats, opacity))
    return jobs


def _map(a: argparse.Namespace) -> int:
    over = bool(a.over_tl or a.over_br or a.over_center or a.over_radius is not None)
    if not 0 <= a.over_opacity <= 1:
        raise ValueError("--over-opacity must be between 0 and 1")

    title = " ".join(a.title.split())  # one line: no newlines, no runs of spaces
    langs = parse_langs(a.lang)
    layers = layer_defs.select(_split(a.layers), _split(a.exclude_layers), _split(a.include_layers))
    tl, br, radius = _corners(a.tl, a.br, a.center, a.radius)
    base_frame = fit(tl, br, a.paper, a.margin, a.orientation, a.shape, radius, bool(title))
    specs = [("a", base_frame, layers, themes.load(a.theme, a.tint), 1.0)]
    if over:
        # Same paper, orientation, margin and title band: the page is the common shape.
        o_tl, o_br, o_radius = _corners(
            a.over_tl, a.over_br, a.over_center, a.over_radius, "--over-"
        )
        over_frame = fit(
            o_tl, o_br, a.paper, a.margin, base_frame.orientation, a.shape, o_radius, bool(title)
        )
        over_layers = layer_defs.select(
            _split(a.over_layers) or [layer.name for layer in layers],
            _split(a.over_exclude_layers),
            _split(a.over_include_layers),
        )
        over_name = a.over_theme or a.theme
        # The tint follows the theme: only a tinted theme inherits --tint.
        over_tint = a.over_tint or (a.tint if over_name in themes.TINTED else None)
        over_theme = themes.load(over_name, over_tint)
        specs.append(("b", over_frame, over_layers, over_theme, a.over_opacity))

    source: Source = PbfSource(a.pbf, a.cache) if a.pbf else OverpassSource(a.cache, a.overpass_url)
    boxes = [frame.lonlat_bounds() for _, frame, *_rest in specs]
    for bounds in boxes:  # fail before downloading anything
        source.check(bounds)
    try:
        jobs = _load_jobs(specs, source, langs, a.cache)
    except OverpassError as err:
        # Overpass has already waited and retried (ADR 0002). If an extract we already have
        # covers every area, carry on with it and say so; never download one unasked.
        local = None if a.pbf else local_pbf_for(boxes, PBF_DIR)
        if local is None:
            raise OverpassError(f"{err}\n{offline_hint(boxes, a.cache)}") from err
        log.warning(
            "Overpass failed (%s); drawing every layer from the local extract %s instead",
            err,
            local,
        )
        source = PbfSource(local, a.cache)
        for bounds in boxes:
            source.check(bounds)
        jobs = _load_jobs(specs, source, langs, a.cache)

    with Spinner("drawing the SVG"):
        svg = render(jobs, a.legend, a.coords, title)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp_beside(a.out)
    try:
        tmp.write_text(svg, encoding="utf-8")
        tmp.replace(a.out)
    finally:
        tmp.unlink(missing_ok=True)
    log.info("wrote %s (%d KiB)", a.out, len(svg) // 1024)
    if a.pdf:
        pdf = a.out.with_suffix(".pdf")
        with Spinner("writing the PDF"):
            svg_to_pdf(a.out, pdf)
        log.info("wrote %s (%d KiB)", pdf, pdf.stat().st_size // 1024)
    return 0


def _download(a: argparse.Namespace) -> int:
    download(a.url, a.out_dir)
    return 0


def _wizard(a: argparse.Namespace) -> int:
    from vectormaps import wizard  # only here: the other commands do not need questionary

    return wizard.run()


def main(argv: list[str] | None = None) -> int:
    handler = ProgressHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    args = build_parser().parse_args(argv)
    try:
        commands = {
            "list": lambda _: _list(),
            "map": _map,
            "download": _download,
            "wizard": _wizard,
        }
        return commands[args.command](args)
    except (ValueError, RuntimeError, OSError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        # Ctrl-C: the caches are written via temp files, so nothing is left half done.
        print("interrupted", file=sys.stderr)
        return 130  # 128 + SIGINT, what shells expect

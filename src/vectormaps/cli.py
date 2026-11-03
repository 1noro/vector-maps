import argparse
import logging
import sys
from pathlib import Path

from vectormaps import geofabrik
from vectormaps import layers as layer_defs
from vectormaps import theme as themes
from vectormaps.area import Frame, fit, parse_corner
from vectormaps.download import PBF_DIR, download
from vectormaps.labels import DEFAULT_LANG, parse_langs
from vectormaps.overpass import OverpassError
from vectormaps.paper import PAPERS
from vectormaps.pdf import svg_to_pdf
from vectormaps.pipeline import load_features
from vectormaps.progress import ProgressHandler, Spinner
from vectormaps.render import LEGENDS, Job, render
from vectormaps.sources import Bounds, OverpassSource, PbfSource, Source, local_pbf_for

log = logging.getLogger("vectormaps")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vectormaps", description="SVG maps from OpenStreetMap, by layers, for print."
    )
    sub = p.add_subparsers(dest="command", required=True)

    m = sub.add_parser(
        "map",
        help="draw an area as SVG, optionally with a second area stacked on top",
        description="Corners are LAT,LON. Use --tl=LAT,LON (with '=') so negative values parse.",
    )
    m.add_argument("--tl", required=True, metavar="LAT,LON", help="top-left corner")
    m.add_argument("--br", required=True, metavar="LAT,LON", help="bottom-right corner")
    m.add_argument("--paper", default="A4", choices=list(PAPERS), type=str.upper)
    m.add_argument("--orientation", default="auto", choices=["auto", "landscape", "portrait"])
    m.add_argument("--margin", type=float, default=10.0, metavar="MM")
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
    m.add_argument("--theme", default="color", help="bundled theme name or a .toml path")
    m.add_argument(
        "--tint",
        metavar="HEX",
        help="colour of the monochrome theme, e.g. #1f3b5c (black becomes it, white stays); "
        f"default: {themes.DEFAULT_TINT}",
    )
    m.add_argument("--out", type=Path, default=Path("out/map.svg"))
    m.add_argument(
        "--pdf", action="store_true", help="also write a PDF of the paper size next to the SVG"
    )
    m.add_argument(
        "--legend",
        choices=LEGENDS,
        default="full",
        help="minimal: only the corners, the scale, a short OSM credit and the mark",
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
    o.add_argument("--over-layers", metavar="A,B", help="default: the ones of the first area")
    o.add_argument("--over-exclude-layers", metavar="A,B", help="leave these out of the overlay")
    o.add_argument("--over-include-layers", metavar="A,B", help="add these to the overlay")
    o.add_argument("--over-theme", help="default: same as --theme")
    o.add_argument("--over-tint", metavar="HEX", help="default: same as --tint")
    o.add_argument("--over-opacity", type=float, default=1.0, metavar="0-1")

    sub.add_parser("list", help="list layers, papers and themes")

    d = sub.add_parser("download", help="download a .osm.pbf extract (e.g. from Geofabrik)")
    d.add_argument("url")
    d.add_argument("--out-dir", type=Path, default=PBF_DIR)
    return p


def _split(text: str | None) -> list[str] | None:
    return [t.strip() for t in text.split(",") if t.strip()] if text else None


def _describe(label: str, frame: Frame) -> str:
    grown = f", grown {frame.growth:.0%} to fit the paper" if frame.growth > 0.005 else ""
    return f"{label}: 1:{frame.scale}, {frame.paper} {frame.orientation}{grown}"


def offline_hint(areas: list[Bounds], cache: Path) -> str:
    """What to do when Overpass fails: the same map from a local extract."""
    again = "repeat the same `make map` adding"
    local = local_pbf_for(areas, PBF_DIR)
    if local is not None:
        return f"hint: {local} already covers this area; {again} PBF={local}"
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
    print("layers:")
    for name in layer_defs.ORDER:
        layer = layer_defs.LAYERS[name]
        extra = "   (not by default)" if name not in layer_defs.DEFAULT else ""
        print(f"  {name:<12} classes (bottom to top): {', '.join(layer.classes)}{extra}")
    print("papers:  ", ", ".join(PAPERS))
    print("themes:  ", ", ".join(themes.available()))
    return 0


def _map(a: argparse.Namespace) -> int:
    if bool(a.over_tl) != bool(a.over_br):
        raise ValueError("--over-tl and --over-br go together")
    if not 0 <= a.over_opacity <= 1:
        raise ValueError("--over-opacity must be between 0 and 1")

    langs = parse_langs(a.lang)
    layers = layer_defs.select(_split(a.layers), _split(a.exclude_layers), _split(a.include_layers))
    base_frame = fit(parse_corner(a.tl), parse_corner(a.br), a.paper, a.margin, a.orientation)
    specs = [("a", base_frame, layers, themes.load(a.theme, a.tint), 1.0)]
    if a.over_tl:
        # Same paper, orientation and margin: the page is the common shape.
        over_frame = fit(
            parse_corner(a.over_tl),
            parse_corner(a.over_br),
            a.paper,
            a.margin,
            base_frame.orientation,
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
    jobs = []
    try:
        for label, frame, lyrs, theme, opacity in specs:
            log.info(_describe(label.upper(), frame))
            feats = load_features(frame, lyrs, source, langs, a.cache)
            jobs.append(Job(label, frame, theme, lyrs, feats, opacity))
    except OverpassError as err:
        raise OverpassError(f"{err}\n{offline_hint(boxes, a.cache)}") from err

    with Spinner("drawing the SVG"):
        svg = render(jobs, a.legend)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.out.with_name(a.out.name + ".tmp")
    tmp.write_text(svg, encoding="utf-8")
    tmp.replace(a.out)
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


def main(argv: list[str] | None = None) -> int:
    handler = ProgressHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    args = build_parser().parse_args(argv)
    try:
        return {"list": lambda _: _list(), "map": _map, "download": _download}[args.command](args)
    except (ValueError, RuntimeError, OSError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        # Ctrl-C: the caches are written via temp files, so nothing is left half done.
        print("interrupted", file=sys.stderr)
        return 130  # 128 + SIGINT, what shells expect

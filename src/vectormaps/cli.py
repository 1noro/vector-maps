import argparse
import logging
import sys
from pathlib import Path

from vectormaps import layers as layer_defs
from vectormaps import theme as themes
from vectormaps.area import Frame, fit, parse_corner
from vectormaps.download import download
from vectormaps.paper import PAPERS
from vectormaps.pipeline import load_features
from vectormaps.render import Job, render
from vectormaps.sources import OverpassSource, PbfSource, Source

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
    m.add_argument("--layers", metavar="A,B", help="default: all, see `vectormaps list`")
    m.add_argument("--theme", default="color", help="bundled theme name or a .toml path")
    m.add_argument("--out", type=Path, default=Path("out/map.svg"))
    m.add_argument("--cache", type=Path, default=Path("data/cache"))
    m.add_argument("--pbf", type=Path, help="read a local .osm.pbf instead of asking Overpass")
    m.add_argument("--overpass-url", help="default: $OVERPASS_URL or the public server")

    o = m.add_argument_group(
        "overlay",
        "A second area drawn over the first on the same page (same paper, own zoom).",
    )
    o.add_argument("--over-tl", metavar="LAT,LON")
    o.add_argument("--over-br", metavar="LAT,LON")
    o.add_argument("--over-layers", metavar="A,B", help="default: same as --layers")
    o.add_argument("--over-theme", help="default: same as --theme")
    o.add_argument("--over-opacity", type=float, default=1.0, metavar="0-1")

    sub.add_parser("list", help="list layers, papers and themes")

    d = sub.add_parser("download", help="download a .osm.pbf extract (e.g. from Geofabrik)")
    d.add_argument("url")
    d.add_argument("--out-dir", type=Path, default=Path("data/pbf"))
    return p


def _split(text: str | None) -> list[str] | None:
    return [t.strip() for t in text.split(",") if t.strip()] if text else None


def _describe(label: str, frame: Frame) -> str:
    grown = f", grown {frame.growth:.0%} to fit the paper" if frame.growth > 0.005 else ""
    return f"{label}: 1:{frame.scale}, {frame.paper} {frame.orientation}{grown}"


def _list() -> int:
    print("layers:")
    for layer in layer_defs.select(None):
        print(f"  {layer.name:<10} classes (bottom to top): {', '.join(layer.classes)}")
    print("papers:  ", ", ".join(PAPERS))
    print("themes:  ", ", ".join(themes.available()))
    return 0


def _map(a: argparse.Namespace) -> int:
    if bool(a.over_tl) != bool(a.over_br):
        raise ValueError("--over-tl and --over-br go together")
    if not 0 <= a.over_opacity <= 1:
        raise ValueError("--over-opacity must be between 0 and 1")

    layers = layer_defs.select(_split(a.layers))
    base_frame = fit(parse_corner(a.tl), parse_corner(a.br), a.paper, a.margin, a.orientation)
    specs = [("a", base_frame, layers, themes.load(a.theme), 1.0)]
    if a.over_tl:
        # Same paper, orientation and margin: the page is the common shape.
        over_frame = fit(
            parse_corner(a.over_tl),
            parse_corner(a.over_br),
            a.paper,
            a.margin,
            base_frame.orientation,
        )
        over_layers = layer_defs.select(_split(a.over_layers)) if a.over_layers else layers
        over_theme = themes.load(a.over_theme or a.theme)
        specs.append(("b", over_frame, over_layers, over_theme, a.over_opacity))

    source: Source = PbfSource(a.pbf, a.cache) if a.pbf else OverpassSource(a.cache, a.overpass_url)
    jobs = []
    for label, frame, lyrs, theme, opacity in specs:
        log.info(_describe(label.upper(), frame))
        feats = load_features(frame, lyrs, source)
        jobs.append(Job(label, frame, theme, lyrs, feats, opacity))

    svg = render(jobs)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.out.with_name(a.out.name + ".tmp")
    tmp.write_text(svg, encoding="utf-8")
    tmp.replace(a.out)
    log.info("wrote %s (%d KiB)", a.out, len(svg) // 1024)
    return 0


def _download(a: argparse.Namespace) -> int:
    download(a.url, a.out_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    args = build_parser().parse_args(argv)
    try:
        return {"list": lambda _: _list(), "map": _map, "download": _download}[args.command](args)
    except (ValueError, RuntimeError, OSError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

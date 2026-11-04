"""A guided way to `vectormaps map`: questions in the terminal instead of flags.

The wizard never draws anything itself (ADR 0009). It turns the answers into the
same argv as the command line and calls `cli.main`, so every check and message is
the CLI's. It also shows the equivalent `make map …`, and remembers the answers in
`data/wizard.json` so the next run starts from the last map.
"""

import contextlib
import dataclasses
import json
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

import questionary
from questionary import Choice

from vectormaps import layers as layer_defs
from vectormaps import theme as themes
from vectormaps.area import MIN_MARGIN_MM, parse_corner
from vectormaps.download import PBF_DIR
from vectormaps.labels import DEFAULT_LANG, parse_langs
from vectormaps.paper import ORIENTATIONS, PAPERS

STATE = Path("data/wizard.json")
OTHER_THEME = "<a .toml file>"


@dataclass
class Area:
    mode: str = "corners"  # corners (tl, br) or center (center, radius)
    tl: str = ""
    br: str = ""
    center: str = ""
    radius: str = ""


@dataclass
class Answers:
    area: Area = field(default_factory=Area)
    paper: str = "A4"
    orientation: str = "landscape"
    shape: str = "rect"
    margin: str = "6"
    layers: list[str] = field(default_factory=lambda: list(layer_defs.DEFAULT))
    theme: str = "bw"
    tint: str = ""  # empty: the default tint; only used by a tinted theme
    lang: str = DEFAULT_LANG
    legend: str = "minimal"
    coords: str = "dms"
    pbf: str = ""  # empty: Overpass
    out: str = "out/map.svg"
    pdf: bool = True
    overlay: bool = False
    over_area: Area = field(default_factory=Area)
    over_layers: list[str] | None = None  # None: the same as the first area
    over_theme: str = ""  # empty: the same as the first area
    over_tint: str = ""
    over_opacity: str = "1"


# --- answers -> command ----------------------------------------------------------------------


def _layer_flags(chosen: list[str], base: tuple[str, ...] | list[str]) -> dict[str, list[str]]:
    """The shortest way to say `chosen` starting from `base`: include/exclude, or the full list."""
    chosen = [n for n in layer_defs.ORDER if n in chosen]
    extra = [n for n in chosen if n not in base]
    missing = [n for n in base if n not in chosen]
    if not extra and not missing:
        return {}
    if len(extra) + len(missing) > len(chosen):
        return {"layers": chosen}
    return {k: v for k, v in (("include", extra), ("exclude", missing)) if v}


def _area_options(area: Area, prefix: str) -> list[tuple[str, str, str]]:
    if area.mode == "center":
        return [
            (f"CENTER{prefix}", "center", area.center),
            (f"RADIUS{prefix}", "radius", area.radius),
        ]
    return [(f"TL{prefix}", "tl", area.tl), (f"BR{prefix}", "br", area.br)]


FLAGS = {"pdf", "no-pdf"}


def options(a: Answers) -> list[tuple[str, str, str]]:
    """(make variable, CLI option, value) for every answer that is not the default.

    The options in FLAGS take no value on the command line (--no-pdf, but PDF=0).
    """
    opts: list[tuple[str, str, str]] = list(_area_options(a.area, ""))
    defaults = Answers()
    for var, name in [
        ("PAPER", "paper"),
        ("ORIENTATION", "orientation"),
        ("SHAPE", "shape"),
        ("MARGIN", "margin"),
    ]:
        if getattr(a, name) != getattr(defaults, name):
            opts.append((var, name, getattr(a, name)))
    names = {"layers": "LAYERS", "include": "INCLUDE_LAYERS", "exclude": "EXCLUDE_LAYERS"}
    flags = {"layers": "layers", "include": "include-layers", "exclude": "exclude-layers"}
    for kind, chosen in _layer_flags(a.layers, layer_defs.DEFAULT).items():
        opts.append((names[kind], flags[kind], ",".join(chosen)))
    if a.theme != defaults.theme:
        opts.append(("THEME", "theme", a.theme))
    if a.tint and a.theme in themes.TINTED:
        opts.append(("TINT", "tint", a.tint))
    if a.lang != defaults.lang:
        opts.append(("LABEL_LANG", "lang", a.lang))
    if a.legend != defaults.legend:
        opts.append(("LEGEND", "legend", a.legend))
    if a.coords != defaults.coords:
        opts.append(("COORDS", "coords", a.coords))
    if a.pbf:
        opts.append(("PBF", "pbf", a.pbf))
    if a.out != defaults.out:
        opts.append(("OUT", "out", a.out))
    if a.pdf != defaults.pdf:
        opts.append(("PDF", "pdf", "1") if a.pdf else ("PDF", "no-pdf", "0"))
    if a.overlay:
        for var, name, value in _area_options(a.over_area, "2"):
            opts.append((var, f"over-{name}", value))
        o_names = {k: f"{v}2" for k, v in names.items()}
        for kind, chosen in _layer_flags(a.over_layers or a.layers, a.layers).items():
            opts.append((o_names[kind], f"over-{flags[kind]}", ",".join(chosen)))
        if a.over_theme:
            opts.append(("THEME2", "over-theme", a.over_theme))
        if a.over_tint and (a.over_theme or a.theme) in themes.TINTED:
            opts.append(("TINT2", "over-tint", a.over_tint))
        if a.over_opacity not in ("", "1", "1.0"):
            opts.append(("OPACITY2", "over-opacity", a.over_opacity))
    return opts


def to_argv(a: Answers) -> list[str]:
    """The arguments of `vectormaps map`, always as --option=value (negative latitudes too)."""
    return ["map"] + [f"--{opt}" if opt in FLAGS else f"--{opt}={v}" for _, opt, v in options(a)]


def to_make(a: Answers) -> str:
    """The `make map …` that draws the same map."""
    parts = [f"{var}={v}" for var, _, v in options(a)]
    return " ".join(["make", "map", *(shlex.quote(p) for p in parts)])


# --- memory ----------------------------------------------------------------------------------


def _strings(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _from_dict(cls, data: dict):
    """A dataclass from a dict, keeping the defaults for what is missing or of the wrong type."""
    obj = cls()
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        value, current = data[f.name], getattr(obj, f.name)
        if dataclasses.is_dataclass(current):
            if isinstance(value, dict):
                setattr(obj, f.name, _from_dict(type(current), value))
        elif f.name == "over_layers":
            if value is None or _strings(value):
                setattr(obj, f.name, value)
        elif isinstance(current, list):
            if _strings(value):
                setattr(obj, f.name, value)
        elif type(value) is type(current):
            setattr(obj, f.name, value)
    return obj


def load(path: Path = STATE) -> Answers:
    """The answers of the last map, or the defaults if there are none (or they are unreadable)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Answers()
    return _from_dict(Answers, data) if isinstance(data, dict) else Answers()


def save(a: Answers, path: Path = STATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(dataclasses.asdict(a), indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


# --- validators: True, or the message to show -----------------------------------------------


def _check(fn):
    def validate(text: str):
        try:
            fn(text)
        except ValueError as err:
            return str(err)
        return True

    return validate


def _positive(text: str) -> None:
    if not float(text) > 0:
        raise ValueError("must be a number above 0")


def _margin(text: str) -> None:
    if float(text) < MIN_MARGIN_MM:
        raise ValueError(f"at least {MIN_MARGIN_MM:g} mm: the attribution lives there")


def _opacity(text: str) -> None:
    if not 0 <= float(text) <= 1:
        raise ValueError("between 0 and 1")


def _svg(text: str) -> None:
    if not text.endswith(".svg"):
        raise ValueError("the output is an .svg file")


def _tint(text: str) -> None:
    if text:
        themes.parse_tint(text)


# --- questions -------------------------------------------------------------------------------


def _select(message: str, choices: list, default=None):
    values = [c.value if isinstance(c, Choice) else c for c in choices]
    return questionary.select(
        message, choices=choices, default=default if default in values else None
    ).unsafe_ask()


def _text(message: str, default: str = "", validate=None, instruction: str | None = None) -> str:
    return questionary.text(
        message, default=default, validate=validate, instruction=instruction
    ).unsafe_ask()


def _ask_area(area: Area, title: str) -> Area:
    mode = _select(
        f"{title}: how do you give it?",
        [
            Choice("two corners (top-left, bottom-right)", "corners"),
            Choice("centre and radius", "center"),
        ],
        area.mode,
    )
    corner = _check(parse_corner)
    hint = "LAT,LON, e.g. 42.8845,-8.5510"
    if mode == "center":
        center = _text("Centre", area.center, corner, hint)
        radius = _text("Radius in km", area.radius, _check(_positive))
        return dataclasses.replace(area, mode=mode, center=center.strip(), radius=radius.strip())
    tl = _text("Top-left corner", area.tl, corner, hint)
    br = _text("Bottom-right corner", area.br, corner, hint)
    return dataclasses.replace(area, mode=mode, tl=tl.strip(), br=br.strip())


def _ask_layers(message: str, chosen: list[str]) -> list[str]:
    notes = {}
    for name in layer_defs.ORDER:
        layer = layer_defs.LAYERS[name]
        if layer.dem:
            notes[name] = "  (relief: downloads ~40 MB per square degree the first time)"
        elif layer.text:
            notes[name] = "  (names)"
    choices = [Choice(n + notes.get(n, ""), n, checked=n in chosen) for n in layer_defs.ORDER]
    return questionary.checkbox(
        message, choices=choices, validate=lambda sel: bool(sel) or "pick at least one layer"
    ).unsafe_ask()


def _ask_theme(message: str, current: str, same: bool = False) -> str:
    choices = ([Choice("the same as the first area", "")] if same else []) + themes.available()
    choices.append(OTHER_THEME)
    bundled = current == "" or current in themes.available()
    name = _select(message, choices, current if bundled else OTHER_THEME)
    if name != OTHER_THEME:
        return name
    return questionary.path(
        "Theme file (.toml)",
        default="" if bundled else current,
        validate=lambda p: p.endswith(".toml") or "a theme is a .toml file",
    ).unsafe_ask()


def ask_area(a: Answers) -> Answers:
    return dataclasses.replace(a, area=_ask_area(a.area, "Area"))


def ask_paper(a: Answers) -> Answers:
    paper = _select("Paper", list(PAPERS), a.paper)
    orientation = _select("Orientation", ["auto", *ORIENTATIONS], a.orientation)
    shape = _select(
        "Shape of the map on the paper",
        [
            Choice("rect: fills the page", "rect"),
            Choice("square, centred", "square"),
            Choice("circle, centred", "circle"),
        ],
        a.shape,
    )
    margin = _text("Margin in mm", a.margin, _check(_margin))
    return dataclasses.replace(
        a, paper=paper, orientation=orientation, shape=shape, margin=margin.strip()
    )


def ask_layers(a: Answers) -> Answers:
    chosen = _ask_layers("Layers (space marks, enter goes on)", a.layers)
    return dataclasses.replace(a, layers=chosen)


def ask_style(a: Answers) -> Answers:
    theme = _ask_theme("Theme", a.theme)
    tint = a.tint
    if theme in themes.TINTED:
        tint = _text(
            "Tint", a.tint, _check(_tint), f"hex colour; empty = {themes.DEFAULT_TINT}"
        ).strip()
    lang = a.lang
    if any(layer_defs.LAYERS[n].text for n in a.layers + (a.over_layers or [])):
        lang = _text(
            "Language of the names", a.lang, _check(parse_langs), "es, gl, en… or gl,es, or local"
        ).strip()
    legend = _select(
        "Legend",
        [
            Choice("minimal: corners, scale, © OSM and the mark", "minimal"),
            Choice("full: also the paper and the full credit", "full"),
        ],
        a.legend,
    )
    coords = _select(
        "Coordinates in the legend",
        [
            Choice("dd   42.88000, -8.54000", "dd"),
            Choice("dm   42°52.800'N 8°32.400'W", "dm"),
            Choice("dms  42°52'48.0\"N 8°32'24.0\"W", "dms"),
        ],
        a.coords,
    )
    return dataclasses.replace(a, theme=theme, tint=tint, lang=lang, legend=legend, coords=coords)


def ask_overlay(a: Answers) -> Answers:
    if not questionary.confirm(
        "Stack a second area on top (same paper, its own zoom)?", default=a.overlay
    ).unsafe_ask():
        return dataclasses.replace(a, overlay=False)
    area = _ask_area(a.over_area, "Second area")
    chosen = _ask_layers("Layers of the second area", a.over_layers or a.layers)
    theme = _ask_theme("Theme of the second area", a.over_theme, same=True)
    tint = a.over_tint
    if (theme or a.theme) in themes.TINTED:
        tint = _text(
            "Tint of the second area", a.over_tint, _check(_tint), "empty = the same as the first"
        ).strip()
    opacity = _text("Opacity of the second area", a.over_opacity, _check(_opacity), "0 to 1")
    return dataclasses.replace(
        a,
        overlay=True,
        over_area=area,
        over_layers=None if chosen == [n for n in layer_defs.ORDER if n in a.layers] else chosen,
        over_theme=theme,
        over_tint=tint,
        over_opacity=opacity.strip(),
    )


def ask_data(a: Answers) -> Answers:
    pbfs = sorted(str(p) for p in PBF_DIR.glob("*.osm.pbf"))
    choices = [Choice("Overpass (online, cached)", "")] + [Choice(p, p) for p in pbfs]
    if a.pbf and a.pbf not in pbfs:
        choices.append(Choice(f"{a.pbf} (not found)", a.pbf))
    if not pbfs:
        print(f"  no extracts in {PBF_DIR}/ (make pbf URL=… downloads one)")
    return dataclasses.replace(a, pbf=_select("Data", choices, a.pbf))


def ask_output(a: Answers) -> Answers:
    out = _text("Output file", a.out, _check(_svg), "the same name overwrites the last one")
    pdf = questionary.confirm("Also a PDF of the paper size?", default=a.pdf).unsafe_ask()
    return dataclasses.replace(a, out=out.strip(), pdf=pdf)


SECTIONS = {
    "area": ask_area,
    "paper": ask_paper,
    "layers": ask_layers,
    "style": ask_style,
    "overlay": ask_overlay,
    "data": ask_data,
    "output": ask_output,
}


def ask_all(a: Answers) -> Answers:
    for ask in SECTIONS.values():
        a = ask(a)
    return a


# --- the loop --------------------------------------------------------------------------------


def generate(a: Answers) -> bool:
    from vectormaps import cli  # here: cli imports this module for the `wizard` command

    try:
        return cli.main(to_argv(a)) == 0
    except SystemExit:  # argparse refused something; it has said what
        return False


def run(state: Path = STATE) -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise ValueError("the wizard needs a terminal: run `make wizard`, or use `make map`")
    a = load(state)
    if not state.exists():
        print("vector-maps wizard: a few questions, then the map. Ctrl-C goes back.")
        try:
            a = ask_all(a)
        except KeyboardInterrupt:
            return 0
    next_step = "generate"
    while True:
        print(f"\n  {to_make(a)}\n")
        choices = [Choice("Generate the map", "generate")]
        choices += [Choice(f"Change: {name}", name) for name in SECTIONS]
        choices += [Choice("Go through all the questions", "all"), Choice("Quit", "quit")]
        try:
            step = _select("What now?", choices, next_step)
        except KeyboardInterrupt:
            return 0
        if step == "quit":
            return 0
        if step == "generate":
            if generate(a):
                save(a, state)
                pdf = f" and {Path(a.out).with_suffix('.pdf')}" if a.pdf else ""
                print(f"done: {a.out}{pdf}")
            next_step = "generate"
            continue
        with contextlib.suppress(KeyboardInterrupt):  # a section left half done changes nothing
            a = ask_all(a) if step == "all" else SECTIONS[step](a)
        next_step = "generate"

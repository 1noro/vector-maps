import json
import re
import shlex
from pathlib import Path

import pytest

from vectormaps import cli, wizard
from vectormaps.layers import DEFAULT
from vectormaps.wizard import Answers, Area

CORNERS = Area(tl="42.8845,-8.5510", br="42.8775,-8.5385")


def parse(a: Answers):
    return cli.build_parser().parse_args(wizard.to_argv(a))


def test_the_defaults_are_only_the_area():
    a = Answers(area=CORNERS)
    assert wizard.to_argv(a) == ["map", "--tl=42.8845,-8.5510", "--br=42.8775,-8.5385"]
    assert wizard.to_make(a) == "make map TL=42.8845,-8.5510 BR=42.8775,-8.5385"


def test_negative_latitudes_parse():
    ns = parse(Answers(area=Area(tl="-33.85,151.20", br="-33.87,151.22")))
    assert ns.tl == "-33.85,151.20"
    assert ns.br == "-33.87,151.22"


def test_centre_and_radius_and_the_rest_of_the_options():
    a = Answers(
        area=Area(mode="center", center="42.88,-8.54", radius="1.5", tl="1,1", br="0,2"),
        paper="A3",
        orientation="portrait",
        shape="circle",
        margin="12",
        theme="monochrome",
        tint="#7a2e1f",
        lang="gl,es",
        legend="minimal",
        coords="dms",
        pbf="data/pbf/galicia-latest.osm.pbf",
        out="out/test.svg",
        pdf=True,
    )
    ns = parse(a)
    assert (ns.center, ns.radius, ns.tl, ns.br) == ("42.88,-8.54", 1.5, None, None)
    assert (ns.paper, ns.orientation, ns.shape, ns.margin) == ("A3", "portrait", "circle", 12.0)
    assert (ns.theme, ns.tint, ns.lang) == ("monochrome", "#7a2e1f", "gl,es")
    assert (ns.legend, ns.coords, ns.pdf) == ("minimal", "dms", True)
    assert ns.pbf == Path("data/pbf/galicia-latest.osm.pbf")
    assert ns.out == Path("out/test.svg")


def test_a_tint_only_goes_with_a_tinted_theme():
    ns = parse(Answers(area=CORNERS, theme="bw", tint="#7a2e1f"))
    assert ns.tint is None


@pytest.mark.parametrize(
    "chosen, flags",
    [
        (list(DEFAULT), {}),
        ([*DEFAULT, "places", "street-names"], {"include": ["street-names", "places"]}),
        ([n for n in DEFAULT if n != "railways"], {"exclude": ["railways"]}),
        (["roads"], {"layers": ["roads"]}),
        (
            [*(n for n in DEFAULT if n != "railways"), "contours"],
            {"include": ["contours"], "exclude": ["railways"]},
        ),
    ],
)
def test_layers_are_said_the_shortest_way(chosen, flags):
    assert wizard._layer_flags(chosen, DEFAULT) == flags


def test_the_chosen_layers_are_the_ones_drawn():
    chosen = ["water", "roads", "street-names"]
    ns = parse(Answers(area=CORNERS, layers=chosen))
    from vectormaps import layers

    picked = layers.select(
        cli._split(ns.layers), cli._split(ns.exclude_layers), cli._split(ns.include_layers)
    )
    assert [layer.name for layer in picked] == chosen


def test_overlay():
    a = Answers(
        area=CORNERS,
        theme="monochrome",
        overlay=True,
        over_area=Area(mode="center", center="42.88,-8.54", radius="0.3"),
        over_layers=["buildings", "roads"],
        over_tint="#000",
        over_opacity="0.6",
    )
    ns = parse(a)
    assert (ns.over_center, ns.over_radius) == ("42.88,-8.54", 0.3)
    assert ns.over_layers == "buildings,roads"
    assert (ns.over_theme, ns.over_tint, ns.over_opacity) == (None, "#000", 0.6)


def test_overlay_off_ignores_its_answers():
    a = Answers(area=CORNERS, over_area=CORNERS, over_opacity="0.5")
    assert all(not arg.startswith("--over") for arg in wizard.to_argv(a))


def test_the_make_command_quotes_what_the_shell_would_eat():
    a = Answers(area=CORNERS, theme="monochrome", tint="#7a2e1f", out="out/my map.svg")
    words = shlex.split(wizard.to_make(a))
    assert "TINT=#7a2e1f" in words
    assert "OUT=out/my map.svg" in words


def test_every_make_variable_is_passed_by_the_makefile_as_its_option():
    makefile = (Path(__file__).parents[1] / "Makefile").read_text(encoding="utf-8")
    passed = dict(re.findall(r"\$\(if \$\((\w+)\),(--[\w-]+)", makefile))
    a = Answers(
        area=CORNERS,
        paper="A3",
        orientation="portrait",
        shape="square",
        margin="8",
        layers=[*(n for n in DEFAULT if n != "railways"), "places"],
        theme="monochrome",
        tint="#123",
        lang="gl",
        legend="minimal",
        coords="dm",
        pbf="x.osm.pbf",
        out="out/x.svg",
        pdf=True,
        overlay=True,
        over_area=Area(mode="center", center="1,1", radius="1"),
        over_layers=["roads", "places", "water", "green", "buildings", "contours"],
        over_theme="monochrome",
        over_tint="#456",
        over_opacity="0.5",
    )
    variables = [var for var, _, _ in wizard.options(a)]
    assert len(variables) > 20
    for var, option, _ in wizard.options(a):
        assert passed.get(var) == f"--{option}", var
    centre_corners = Answers(
        area=Area(mode="center", center="1,1", radius="1"), overlay=True, over_area=CORNERS
    )
    for var, option, _ in wizard.options(centre_corners):
        assert passed.get(var) == f"--{option}", var


def test_the_answers_are_remembered(tmp_path):
    path = tmp_path / "wizard.json"
    a = Answers(area=CORNERS, paper="A3", layers=["roads"], overlay=True, over_layers=["water"])
    wizard.save(a, path)
    assert wizard.load(path) == a


@pytest.mark.parametrize(
    "content",
    ["", "not json", "[1, 2]", '{"paper": 3, "layers": "roads", "area": "x", "pdf": "yes"}'],
)
def test_a_bad_memory_falls_back_to_the_defaults(tmp_path, content):
    path = tmp_path / "wizard.json"
    path.write_text(content, encoding="utf-8")
    assert wizard.load(path) == Answers()


def test_a_memory_from_an_older_version_keeps_what_it_can(tmp_path):
    path = tmp_path / "wizard.json"
    path.write_text(json.dumps({"paper": "A2", "gone": 1, "area": {"tl": "1,1"}}), "utf-8")
    a = wizard.load(path)
    assert (a.paper, a.area.tl, a.area.mode, a.theme) == ("A2", "1,1", "corners", "color")


def test_no_memory_is_the_defaults(tmp_path):
    assert wizard.load(tmp_path / "none.json") == Answers()


def test_without_a_terminal_it_says_what_to_do(capsys):
    assert cli.main(["wizard"]) == 1
    assert "make wizard" in capsys.readouterr().err


def test_generate_runs_the_cli_with_the_answers(monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "_map", lambda ns: seen.append(ns) or 0)
    assert wizard.generate(Answers(area=CORNERS, paper="A5"))
    assert seen[0].paper == "A5"


def test_generate_reports_a_failure(monkeypatch, capsys):
    assert not wizard.generate(Answers(area=Area(tl="1,1", br="2,2")))  # TL south of BR
    assert capsys.readouterr().err.startswith("error: ")

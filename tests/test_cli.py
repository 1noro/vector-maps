from pathlib import Path

import pytest

from vectormaps import cli
from vectormaps.geofabrik import Region
from vectormaps.overpass import OverpassError


def test_ctrl_c_exits_quietly(monkeypatch, capsys):
    def interrupted():
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_list", interrupted)
    assert cli.main(["list"]) == 130
    err = capsys.readouterr().err
    assert "interrupted" in err
    assert "Traceback" not in err


def test_user_errors_have_no_traceback(capsys):
    assert cli.main(["map", "--tl=1,1", "--br=2,2"]) == 1  # TL south of BR
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert "Traceback" not in err


def fail_overpass(*args):
    raise OverpassError("Overpass answered HTTP 504")


MAP = ["map", "--tl=42.8845,-8.5510", "--br=42.8775,-8.5385"]


def test_overpass_failing_suggests_a_local_pbf_it_already_has(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_features", fail_overpass)
    monkeypatch.setattr(cli, "local_pbf_for", lambda b, d: Path("data/pbf/galicia-latest.osm.pbf"))
    assert cli.main([*MAP, f"--cache={tmp_path}"]) == 1
    err = capsys.readouterr().err
    assert "HTTP 504" in err
    assert "adding PBF=data/pbf/galicia-latest.osm.pbf" in err
    assert "make pbf" not in err


def test_overpass_failing_suggests_the_geofabrik_extract(tmp_path, monkeypatch, capsys):
    url = "https://download.geofabrik.de/europe/spain/galicia-latest.osm.pbf"
    monkeypatch.setattr(cli, "load_features", fail_overpass)
    monkeypatch.setattr(cli, "local_pbf_for", lambda b, d: None)
    monkeypatch.setattr(cli.geofabrik, "region_for", lambda b, c: Region("Galicia", url))
    assert cli.main([*MAP, f"--cache={tmp_path}"]) == 1
    err = capsys.readouterr().err
    assert f"make pbf URL={url}" in err
    assert "adding PBF=data/pbf/galicia-latest.osm.pbf" in err


def test_overpass_failing_without_a_known_extract_points_to_the_list(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_features", fail_overpass)
    monkeypatch.setattr(cli, "local_pbf_for", lambda b, d: None)
    monkeypatch.setattr(cli.geofabrik, "region_for", lambda b, c: None)
    assert cli.main([*MAP, f"--cache={tmp_path}"]) == 1
    assert "https://download.geofabrik.de/" in capsys.readouterr().err


@pytest.mark.parametrize(
    "args, message",
    [
        (["--tl=1,1", "--br=0,2", "--center=1,1", "--radius=2"], "either"),
        (["--center=1,1"], "go together"),
        (["--radius=2"], "go together"),
        ([], "give the area"),
        (["--center=1,1", "--radius=0"], "radius"),
        (["--tl=2,1", "--br=1,2", "--over-center=1,1"], "--over-center and --over-radius"),
    ],
)
def test_the_area_is_corners_or_centre_and_radius(args, message, capsys):
    assert cli.main(["map", *args]) == 1
    err = capsys.readouterr().err
    assert message in err
    assert "Traceback" not in err

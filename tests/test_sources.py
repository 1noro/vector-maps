"""Integration tests with osmium on a tiny hand-written OSM file. No network."""

from pathlib import Path

import pytest

from vectormaps import osmexport
from vectormaps.area import fit
from vectormaps.layers import select
from vectormaps.pipeline import load_features
from vectormaps.sources import PbfSource, local_pbf_for

# A building (closed way) and a lake with an island (multipolygon with a hole),
# plus a street; around 42.880 N, 8.545 W.
OSM = """<?xml version='1.0' encoding='UTF-8'?>
<osm version='0.6' generator='test'>
  <node id='1' lat='42.8800' lon='-8.5450' version='1'/>
  <node id='2' lat='42.8800' lon='-8.5445' version='1'/>
  <node id='3' lat='42.8804' lon='-8.5445' version='1'/>
  <node id='4' lat='42.8804' lon='-8.5450' version='1'/>
  <node id='10' lat='42.8810' lon='-8.5460' version='1'/>
  <node id='11' lat='42.8810' lon='-8.5440' version='1'/>
  <node id='12' lat='42.8820' lon='-8.5440' version='1'/>
  <node id='13' lat='42.8820' lon='-8.5460' version='1'/>
  <node id='14' lat='42.8813' lon='-8.5455' version='1'/>
  <node id='15' lat='42.8813' lon='-8.5450' version='1'/>
  <node id='16' lat='42.8817' lon='-8.5450' version='1'/>
  <node id='17' lat='42.8817' lon='-8.5455' version='1'/>
  <node id='20' lat='42.8795' lon='-8.5460' version='1'/>
  <node id='21' lat='42.8795' lon='-8.5440' version='1'/>
  <node id='30' lat='42.8808' lon='-8.5452' version='1'>
    <tag k='place' v='suburb'/>
    <tag k='name' v='A Almáciga'/>
    <tag k='name:es' v='La Almáciga'/>
  </node>
  <way id='100' version='1'>
    <nd ref='1'/><nd ref='2'/><nd ref='3'/><nd ref='4'/><nd ref='1'/>
    <tag k='building' v='yes'/>
  </way>
  <way id='101' version='1'>
    <nd ref='10'/><nd ref='11'/><nd ref='12'/><nd ref='13'/><nd ref='10'/>
  </way>
  <way id='102' version='1'>
    <nd ref='14'/><nd ref='15'/><nd ref='16'/><nd ref='17'/><nd ref='14'/>
  </way>
  <way id='103' version='1'>
    <nd ref='20'/><nd ref='21'/>
    <tag k='highway' v='residential'/>
    <tag k='name' v='Rúa do Vilar'/>
    <tag k='name:es' v='Calle del Vilar'/>
  </way>
  <relation id='200' version='1'>
    <member type='way' ref='101' role='outer'/>
    <member type='way' ref='102' role='inner'/>
    <tag k='type' v='multipolygon'/>
    <tag k='natural' v='water'/>
  </relation>
</osm>
"""
TL, BR = (42.8825, -8.5465), (42.8790, -8.5435)


@pytest.fixture
def osm_file(tmp_path: Path) -> Path:
    path = tmp_path / "mini.osm"
    path.write_text(OSM)
    return path


def test_export_assembles_multipolygons(osm_file, tmp_path):
    out = osmexport.export(osm_file, tmp_path / "mini.geojsonseq")
    feats = list(osmexport.read_features(out))
    kinds = [
        (k, t.get("building") or t.get("natural") or t.get("highway") or t.get("place"))
        for k, t, _ in feats
    ]
    assert ("polygon", "yes") in kinds
    assert ("polygon", "water") in kinds
    assert ("line", "residential") in kinds
    assert ("point", "suburb") in kinds  # place names need the points
    lake = next(g for k, t, g in feats if t.get("natural") == "water")
    assert len(lake.geoms) == 1 and len(lake.geoms[0].interiors) == 1  # the island is a hole


def test_pbf_source_cuts_classifies_and_caches(osm_file, tmp_path):
    frame = fit(TL, BR, "A4")
    layers = select(["water", "buildings", "roads"])
    cache = tmp_path / "cache"
    feats = load_features(frame, layers, PbfSource(osm_file, cache))
    assert [i.cls for i in feats["buildings"]] == ["building"]
    assert [i.cls for i in feats["water"]] == ["water"]
    assert [i.cls for i in feats["roads"]] == ["minor"]
    assert list((cache / "pbf").glob("*.geojsonseq"))  # cut once, cached
    assert not list((cache / "pbf").glob("*.osm.pbf"))  # the intermediate is removed
    again = load_features(frame, layers, PbfSource(osm_file, cache))
    assert {k: len(v) for k, v in again.items()} == {k: len(v) for k, v in feats.items()}


def test_pbf_source_needs_the_file(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        PbfSource(tmp_path / "nope.osm.pbf", tmp_path)


@pytest.fixture
def pbf_with_box(tmp_path):
    """A real PBF whose header carries a box, as Geofabrik's do."""
    import subprocess

    bounds = "<bounds minlat='42.8790' minlon='-8.5465' maxlat='42.8825' maxlon='-8.5435'/>"
    xml = tmp_path / "boxed.osm"
    xml.write_text(OSM.replace("generator='test'>", f"generator='test'>{bounds}"))
    out = tmp_path / "mini.osm.pbf"
    subprocess.run(["osmium", "cat", xml, "-o", out], check=True, capture_output=True)
    return out


def test_pbf_reads_the_box_from_its_header(pbf_with_box, tmp_path):
    w, s, e, n = PbfSource(pbf_with_box, tmp_path).coverage
    assert (w, s, e, n) == pytest.approx((-8.5465, 42.8790, -8.5435, 42.8825), abs=1e-6)


def test_a_local_pbf_is_found_only_if_it_holds_the_whole_area(pbf_with_box, tmp_path):
    inside = (42.8795, -8.5460, 42.8820, -8.5440)
    sticks_out = (42.8800, -8.5460, 42.8830, -8.5420)
    assert local_pbf_for([inside], pbf_with_box.parent) == pbf_with_box
    assert local_pbf_for([inside, sticks_out], pbf_with_box.parent) is None
    assert local_pbf_for([inside], tmp_path / "empty") is None


def test_pbf_without_a_box_cannot_be_checked(osm_file, tmp_path):
    source = PbfSource(osm_file, tmp_path)
    assert source.coverage is None
    source.check((35.6, 139.7, 35.7, 139.8))  # nothing to compare with: no error


def test_area_outside_the_pbf_is_an_error(pbf_with_box, tmp_path):
    tokyo = (35.66, 139.70, 35.71, 139.78)  # south, west, north, east
    with pytest.raises(ValueError, match=r"outside mini\.osm\.pbf.*make pbf"):
        PbfSource(pbf_with_box, tmp_path).check(tokyo)


def test_area_partly_outside_the_pbf_warns(pbf_with_box, tmp_path, caplog):
    source = PbfSource(pbf_with_box, tmp_path)
    source.check((42.8800, -8.5460, 42.8830, -8.5420))  # sticks out to the north and east
    assert "only" in caplog.text and "inside mini.osm.pbf" in caplog.text
    caplog.clear()
    source.check((42.8795, -8.5460, 42.8820, -8.5440))  # fully inside
    assert caplog.text == ""


def test_no_data_in_the_area_warns(caplog):
    class Empty:
        def check(self, bounds):
            pass

        def features(self, layer, bounds):
            return []

    load_features(fit(TL, BR, "A4"), select(["roads"]), Empty())
    assert "no data found" in caplog.text


def test_labels_come_out_in_the_chosen_language(osm_file, tmp_path):
    frame = fit(TL, BR, "A4")
    layers = select(["street-names", "places"])
    es = load_features(frame, layers, PbfSource(osm_file, tmp_path / "c1"), ["es"])
    assert [i.text for i in es["street-names"]] == ["Calle del Vilar"]
    assert [i.text for i in es["places"]] == ["La Almáciga"]
    gl = load_features(frame, layers, PbfSource(osm_file, tmp_path / "c2"), ["gl", "local"])
    assert [i.text for i in gl["street-names"]] == ["Rúa do Vilar"]  # no name:gl: the mapped one
    assert [i.text for i in gl["places"]] == ["A Almáciga"]

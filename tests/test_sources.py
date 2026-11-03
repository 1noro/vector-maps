"""Integration tests with osmium on a tiny hand-written OSM file. No network."""

from pathlib import Path

import pytest

from vectormaps import osmexport
from vectormaps.area import fit
from vectormaps.layers import select
from vectormaps.pipeline import load_features
from vectormaps.sources import PbfSource

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
    kinds = [(k, t.get("building") or t.get("natural") or t.get("highway")) for k, t, _ in feats]
    assert ("polygon", "yes") in kinds
    assert ("polygon", "water") in kinds
    assert ("line", "residential") in kinds
    lake = next(g for k, t, g in feats if t.get("natural") == "water")
    assert len(lake.geoms) == 1 and len(lake.geoms[0].interiors) == 1  # the island is a hole


def test_pbf_source_cuts_classifies_and_caches(osm_file, tmp_path):
    frame = fit(TL, BR, "A4")
    layers = select(["water", "buildings", "roads"])
    cache = tmp_path / "cache"
    feats = load_features(frame, layers, PbfSource(osm_file, cache))
    assert [c for c, _ in feats["buildings"]] == ["building"]
    assert [c for c, _ in feats["water"]] == ["water"]
    assert [c for c, _ in feats["roads"]] == ["minor"]
    assert list((cache / "pbf").glob("*.geojsonseq"))  # cut once, cached
    assert not list((cache / "pbf").glob("*.osm.pbf"))  # the intermediate is removed
    again = load_features(frame, layers, PbfSource(osm_file, cache))
    assert {k: len(v) for k, v in again.items()} == {k: len(v) for k, v in feats.items()}


def test_pbf_source_needs_the_file(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        PbfSource(tmp_path / "nope.osm.pbf", tmp_path)

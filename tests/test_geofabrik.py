import json
import urllib.error

from vectormaps import geofabrik


def region(name, w, s, e, n):
    ring = [[w, s], [e, s], [e, n], [w, n], [w, s]]
    return {
        "type": "Feature",
        "properties": {
            "id": name.lower(),
            "name": name,
            "urls": {"pbf": f"https://x/{name}.osm.pbf"},
        },
        "geometry": {"type": "MultiPolygon", "coordinates": [[ring]]},
    }


def write_index(cache, *features):
    path = cache / "geofabrik" / "index-v1.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": list(features)}))


SANTIAGO = (42.87, -8.56, 42.89, -8.53)  # south, west, north, east


def test_the_smallest_region_that_holds_the_area_wins(tmp_path):
    write_index(
        tmp_path,
        region("Spain", -9.5, 35.0, 4.5, 44.0),
        region("Galicia", -9.4, 41.8, -6.7, 43.8),
        region("Asturias", -7.2, 42.8, -4.5, 43.7),
    )
    found = geofabrik.region_for([SANTIAGO], tmp_path)
    assert found.name == "Galicia"
    assert found.filename == "Galicia.osm.pbf"


def test_an_area_no_region_holds_gives_nothing(tmp_path):
    write_index(tmp_path, region("Galicia", -9.4, 41.8, -6.7, 43.8))
    assert geofabrik.region_for([(35.6, 139.7, 35.7, 139.8)], tmp_path) is None


def test_without_network_there_is_no_region_and_nothing_cached(tmp_path, monkeypatch):
    def offline(req, timeout):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(geofabrik.urllib.request, "urlopen", offline)
    assert geofabrik.region_for([SANTIAGO], tmp_path) is None
    assert not (tmp_path / "geofabrik" / "index-v1.json").exists()


def test_two_zones_are_held_one_by_one_not_by_the_box_around_both(tmp_path):
    # An L-shaped country: the box around its two zones would reach outside it.
    ring = [[0, 0], [10, 0], [10, 2], [2, 2], [2, 10], [0, 10], [0, 0]]
    l_shape = region("L", 0, 0, 0, 0)
    l_shape["geometry"]["coordinates"] = [[ring]]
    write_index(tmp_path, region("Continent", -50, -50, 50, 50), l_shape)
    zones = [(0.5, 8.0, 1.5, 9.0), (8.0, 0.5, 9.0, 1.5)]  # south, west, north, east
    assert geofabrik.region_for(zones, tmp_path).name == "L"

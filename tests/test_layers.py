import pytest

from vectormaps.layers import LAYERS, select
from vectormaps.theme import available, load


def test_classify_by_geometry_and_tags():
    assert LAYERS["roads"].classify("line", {"highway": "residential"}) == "minor"
    assert LAYERS["roads"].classify("line", {"highway": "primary_link"}) == "major"
    assert LAYERS["roads"].classify("polygon", {"highway": "pedestrian"}) is None
    assert LAYERS["water"].classify("polygon", {"natural": "water"}) == "water"
    assert LAYERS["water"].classify("line", {"waterway": "river"}) == "river"
    assert LAYERS["buildings"].classify("polygon", {"building": "yes"}) == "building"
    assert LAYERS["buildings"].classify("polygon", {"building": "no"}) is None
    assert LAYERS["buildings"].classify("polygon", {"amenity": "bench"}) is None


def test_select_returns_drawing_order():
    assert [layer.name for layer in select(["roads", "water"])] == ["water", "roads"]
    assert [layer.name for layer in select(None)][0] == "water"


def test_select_rejects_unknown():
    with pytest.raises(ValueError, match="nope"):
        select(["water", "nope"])


def test_overpass_query():
    q = LAYERS["buildings"].overpass_query((42.1, -8.5, 42.2, -8.4))
    assert '["building"]["building"!~"^(no)$"](42.10000,-8.50000,42.20000,-8.40000)' in q
    assert 'relation["type"="multipolygon"]' in q
    assert "(._;>;);" in q
    roads = LAYERS["roads"].overpass_query((1, 2, 3, 4))
    assert "relation" not in roads  # lines only: no multipolygon relations


@pytest.mark.parametrize("name", available())
def test_every_theme_styles_every_class(name):
    theme = load(name)
    for layer in LAYERS.values():
        for cls in layer.classes:
            theme.style(layer.name, cls)


def test_unknown_theme():
    with pytest.raises(ValueError):
        load("nope")

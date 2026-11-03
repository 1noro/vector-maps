import pytest

from vectormaps.area import fit, parse_corner, utm_crs
from vectormaps.paper import paper_size

# Roughly 1.0 km wide and 0.8 km high, in Santiago de Compostela.
TL = (42.8845, -8.5510)
BR = (42.8775, -8.5385)


def test_parse_corner():
    assert parse_corner("42.88,-8.54") == (42.88, -8.54)
    assert parse_corner("-33.8, 151.2") == (-33.8, 151.2)


@pytest.mark.parametrize("bad", ["42.88", "a,b", "91,0", "0,181", "1,2,3"])
def test_parse_corner_rejects(bad):
    with pytest.raises(ValueError):
        parse_corner(bad)


def test_paper_sizes():
    assert paper_size("A4", "portrait") == (210, 297)
    assert paper_size("a3", "landscape") == (420, 297)
    with pytest.raises(ValueError):
        paper_size("B5", "portrait")


def test_utm_hemispheres():
    assert utm_crs(-8.5, 42.8).to_epsg() == 32629
    assert utm_crs(151.2, -33.8).to_epsg() == 32756


@pytest.mark.parametrize("paper", ["A5", "A4", "A3", "A2", "A1", "A0"])
def test_frame_has_the_shape_of_the_paper(paper):
    f = fit(TL, BR, paper, margin=10)
    ratio = (f.xmax - f.xmin) / (f.ymax - f.ymin)
    assert ratio == pytest.approx(f.map_w / f.map_h)
    assert f.orientation == "landscape"


def test_frame_never_crops_the_requested_area():
    f = fit(TL, BR, "A4")
    south, west, north, east = f.lonlat_bounds(pad=0)
    assert north >= TL[0] and south <= BR[0]
    assert west <= TL[1] and east >= BR[1]
    assert f.growth >= 0


def test_printed_corners_given_back_hold_the_whole_map():
    # In UTM the lat/lon box between the printed corners is slightly turned, so
    # it grows a little (~2 %) on the way back: never crops, never the same.
    f = fit(TL, BR, "A4")
    g = fit(*f.corners(), "A4")
    assert g.xmin <= f.xmin and g.xmax >= f.xmax
    assert g.ymin <= f.ymin and g.ymax >= f.ymax
    assert g.orientation == f.orientation
    assert g.scale == pytest.approx(f.scale, rel=0.05)


def test_orientation_auto_follows_the_area():
    tall = fit((42.90, -8.55), (42.88, -8.545), "A4")
    assert tall.orientation == "portrait"
    forced = fit(TL, BR, "A4", orientation="portrait")
    assert forced.orientation == "portrait"


def test_same_paper_different_zoom_share_the_page():
    """The overlay relies on this: two areas, one page, two scales."""
    wide = fit(TL, BR, "A4")
    close = fit((42.8830, -8.5470), (42.8815, -8.5440), "A4", orientation=wide.orientation)
    assert (wide.page_w, wide.page_h, wide.margin) == (close.page_w, close.page_h, close.margin)
    assert close.scale < wide.scale


def test_scale_is_metres_per_paper_mm():
    f = fit(TL, BR, "A4")
    assert f.scale == round((f.xmax - f.xmin) / f.map_w * 1000)
    assert 3000 < f.scale < 8000


@pytest.mark.parametrize(
    "tl,br",
    [((42.0, -8.5), (42.1, -8.4)), ((42.1, -8.4), (42.0, -8.5))],
)
def test_corners_must_be_in_order(tl, br):
    with pytest.raises(ValueError):
        fit(tl, br, "A4")


def test_margin_must_leave_room_for_the_attribution():
    with pytest.raises(ValueError):
        fit(TL, BR, "A4", margin=2)

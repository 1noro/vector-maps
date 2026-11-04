import math

import pytest
from pyproj import Transformer

from vectormaps.area import corners_around, fit, parse_corner, utm_crs
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


def test_circle_around_a_centre_is_always_fully_shown():
    centre = (42.8805, -8.5448)
    for paper in ("A5", "A3"):
        f = fit(*corners_around(centre, 2.0), paper)
        south, west, north, east = f.lonlat_bounds(pad=0)
        # the circle of 2 km (~0.018 deg lat) fits in the frame in every direction
        assert north >= centre[0] + 0.0179 and south <= centre[0] - 0.0179
        assert east >= centre[1] + 0.0243 and west <= centre[1] - 0.0243 / 1.0
        assert f.growth >= 0


def test_radius_sets_the_size_of_the_area():
    f = fit(*corners_around((42.88, -8.54), 1.0), "A4")
    # a 2 km square on an A4 landscape page (277 x 190 mm): 2 km fit in the short side
    assert f.ymax - f.ymin == pytest.approx(2000, rel=0.03)


@pytest.mark.parametrize("radius", [0, -1, float("nan")])
def test_radius_must_be_positive(radius):
    with pytest.raises(ValueError, match="radius"):
        corners_around((42.88, -8.54), radius)


def test_rect_is_the_default_shape():
    f = fit(TL, BR, "A4")
    assert f.shape == "rect"
    assert (f.map_x, f.map_y) == (f.margin, f.margin)
    assert (f.map_w, f.map_h) == (f.print_w, f.print_h)


@pytest.mark.parametrize("paper", ["A5", "A4", "A0"])
def test_circle_and_square_boxes_are_squares_centred_on_the_page(paper):
    for shape in ("square", "circle"):
        f = fit(TL, BR, paper, shape=shape)
        assert f.map_w == f.map_h == min(f.print_w, f.print_h)
        assert f.map_x + f.map_w / 2 == pytest.approx(f.page_w / 2)
        assert f.map_y + f.map_h / 2 == pytest.approx(f.page_h / 2)
        assert (f.xmax - f.xmin) == pytest.approx(f.ymax - f.ymin)


def test_circle_holds_the_corners_of_the_requested_area():
    f = fit(TL, BR, "A4", shape="circle")
    south, west, north, east = f.lonlat_bounds(pad=0)
    # the box is the circumscribed square: the whole requested rectangle is inside it
    assert north >= TL[0] and south <= BR[0] and west <= TL[1] and east >= BR[1]
    # and the diameter is the diagonal of the area: its corners sit on the circle
    to_utm = Transformer.from_crs(4326, f.crs, always_xy=True)
    (x1, y1), (x2, y2) = to_utm.transform(TL[1], TL[0]), to_utm.transform(BR[1], BR[0])
    assert f.xmax - f.xmin == pytest.approx(math.hypot(x2 - x1, y2 - y1), rel=0.03)


def test_square_holds_the_longest_side():
    f = fit(TL, BR, "A4", shape="square")
    wide = fit(TL, BR, "A4", orientation="landscape")
    assert f.xmax - f.xmin == pytest.approx(f.ymax - f.ymin)
    assert f.xmax - f.xmin >= (wide.ymax - wide.ymin) * 0.99  # not narrower than the area


def test_circle_with_a_radius_is_exactly_that_circle():
    f = fit(*corners_around((42.88, -8.54), 2.0), "A4", shape="circle", radius_km=2.0)
    assert f.xmax - f.xmin == pytest.approx(4000)
    assert f.growth == 0
    # A4 landscape: 190 mm for 4 km
    assert f.scale == pytest.approx(4000 / 190 * 1000, rel=0.001)


def test_page_matrix_puts_the_box_on_the_page():
    f = fit(TL, BR, "A4", shape="circle")
    a, _, _, e, xoff, yoff = f.page_matrix()
    assert a * f.xmin + xoff == pytest.approx(f.map_x)
    assert e * f.ymax + yoff == pytest.approx(f.map_y)
    assert a * f.xmax + xoff == pytest.approx(f.map_x + f.map_w)


def test_unknown_shape():
    with pytest.raises(ValueError, match="shape"):
        fit(TL, BR, "A4", shape="triangle")

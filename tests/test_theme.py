import pytest

from vectormaps import theme


def test_monochrome_is_bw_tinted_black_to_the_colour_white_stays():
    bw = theme.load("bw")
    mono = theme.load("monochrome", "#204060")
    assert mono.name == "monochrome"
    assert mono.page["background"] == "#ffffff"
    assert mono.page["ink"] == "#204060"
    assert mono.style("roads", "major")["stroke"] == "#204060"
    assert mono.style("places", "city")["stroke"] == "#ffffff"  # the halo
    # The rest is the same as bw: widths, dashes, fonts.
    same = [("roads", "path", "stroke-dasharray"), ("roads", "major", "stroke-width")]
    for layer, cls, key in same:
        assert mono.style(layer, cls)[key] == bw.style(layer, cls)[key]


def test_greys_become_lighter_shades_of_the_tint():
    mono = theme.load("monochrome", "#204060")
    fill = mono.style("buildings", "building")["fill"]  # #bdbdbd in bw
    r, g, b = theme.parse_tint(fill)
    assert 0x20 < r < g < b < 0xFF  # lighter, and still bluish


def test_tint_can_be_short_or_without_the_hash():
    assert theme.parse_tint("1f3b5c") == theme.parse_tint("#1F3B5C") == (0x1F, 0x3B, 0x5C)
    assert theme.parse_tint("#fa0") == (0xFF, 0xAA, 0x00)


@pytest.mark.parametrize("bad", ["blue", "#12345", "#gggggg"])
def test_a_bad_tint_says_what_it_wants(bad):
    with pytest.raises(ValueError, match="hex colour"):
        theme.load("monochrome", bad)


def test_monochrome_has_a_default_tint_and_is_listed():
    assert theme.load("monochrome").page["ink"] == theme.DEFAULT_TINT
    assert "monochrome" in theme.available()


def test_a_tint_only_goes_with_monochrome():
    with pytest.raises(ValueError, match="monochrome"):
        theme.load("color", "#204060")

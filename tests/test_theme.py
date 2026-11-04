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


def test_monochrome_tints_the_casing_too(tmp_path):
    plain = tmp_path / "cased.toml"
    plain.write_text(
        '[page]\nbackground = "#ffffff"\nink = "#000000"\n'
        '[layers.roads.minor]\nstroke = "#ffffff"\ncasing-color = "#000000"\n'
    )
    t = theme.tinted(theme.load(str(plain)), "#204060", "monochrome")
    assert t.style("roads", "minor")["casing-color"] == "#204060"


def _write(tmp_path, body):
    path = tmp_path / "t.toml"
    path.write_text('[page]\nbackground = "#ffffff"\nink = "#000000"\n' + body)
    return str(path)


def test_a_style_cannot_name_a_pattern_the_theme_lacks(tmp_path):
    path = _write(tmp_path, '[layers.water.water]\nfill = "pattern:nope"\n')
    with pytest.raises(ValueError, match=r"no \[patterns.nope\]"):
        theme.load(path)


@pytest.mark.parametrize(
    "pattern, message",
    [('kind = "stars"\nspacing = 1', "kind"), ('kind = "lines"\nspacing = 0', "spacing")],
)
def test_a_pattern_needs_a_known_kind_and_a_spacing(tmp_path, pattern, message):
    path = _write(tmp_path, f"[patterns.p]\n{pattern}\n[layers.water.water]\nfill = 'pattern:p'\n")
    with pytest.raises(ValueError, match=message):
        theme.load(path)


def test_monochrome_tints_the_patterns_too(tmp_path):
    path = _write(
        tmp_path,
        '[patterns.p]\nkind = "lines"\nspacing = 1\ncolor = "#000000"\n'
        '[layers.water.water]\nfill = "pattern:p"\n',
    )
    t = theme.tinted(theme.load(path), "#204060", "monochrome")
    assert t.patterns["p"]["color"] == "#204060"


@pytest.mark.parametrize(
    "shade, message",
    [
        ('style = "stripes"', "shade, hatch"),
        ('style = "hatch"', "needs bands"),
        ('style = "hatch"\nbands = [{ slope = 6 }]', "spacing"),
    ],
)
def test_a_hillshade_style_must_be_known_and_a_hatch_needs_bands(tmp_path, shade, message):
    path = _write(tmp_path, f"[layers.hillshade.shade]\n{shade}\n")
    with pytest.raises(ValueError, match=message):
        theme.load(path)


def test_monochrome_tints_the_hatch_bands_too(tmp_path):
    path = _write(
        tmp_path,
        '[layers.hillshade.shade]\nstyle = "hatch"\n'
        'bands = [{ slope = 6, spacing = 1, color = "#000000" }]\n',
    )
    t = theme.tinted(theme.load(path), "#204060", "monochrome")
    assert t.style("hillshade", "shade")["bands"][0]["color"] == "#204060"


def test_vintage_hatches_its_hills():
    assert theme.load("vintage").style("hillshade", "shade")["style"] == "hatch"


def _colours(value):
    if isinstance(value, dict):
        return [c for v in value.values() for c in _colours(v)]
    if isinstance(value, list):
        return [c for v in value for c in _colours(v)]
    return [value.lower()] if isinstance(value, str) and value.startswith("#") else []


def test_vintage_bw_is_only_black_and_white_with_no_opacity():
    t = theme.load("vintage-bw")
    styles = [t.page, t.patterns, t.layers]
    assert set(_colours(styles)) == {"#000000", "#ffffff"}
    for classes in t.layers.values():
        for style in classes.values():
            assert not any("opacity" in key for key in style)

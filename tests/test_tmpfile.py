from pathlib import Path

from vectormaps.tmpfile import tmp_beside


def test_each_call_gives_a_new_name_next_to_the_file_with_its_extensions():
    target = Path("cache/abc.osm.pbf")
    one, two = tmp_beside(target), tmp_beside(target)
    assert one != two
    assert one.parent == target.parent
    assert one.name.startswith("abc.") and one.name.endswith(".tmp.osm.pbf")

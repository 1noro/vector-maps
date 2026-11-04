import email.utils
import fcntl
import http.client
import io
import logging
import threading
import time
import urllib.error
import urllib.parse

import pytest

from vectormaps import overpass


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def test_fetch_downloads_once_then_uses_the_cache(tmp_path, monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(req)
        return FakeResponse(b"<osm version='0.6'></osm>")

    monkeypatch.setattr(overpass.urllib.request, "urlopen", fake_urlopen)
    first = overpass.fetch("q", tmp_path, url="http://x", sleep=lambda s: None)
    second = overpass.fetch("q", tmp_path, url="http://x", sleep=lambda s: None)
    assert first == second and first.read_text().startswith("<osm")
    assert len(calls) == 1
    assert calls[0].get_header("User-agent").startswith("vector-maps/")


def test_fetch_waits_and_retries_on_429(tmp_path, monkeypatch):
    waits = []
    answers = [
        urllib.error.HTTPError("http://x", 429, "busy", {"Retry-After": "7"}, None),
        FakeResponse(b"<osm></osm>"),
    ]

    def fake_urlopen(req, timeout):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr(overpass.urllib.request, "urlopen", fake_urlopen)
    overpass.fetch("q", tmp_path, url="http://x", sleep=waits.append)
    assert waits[0] == 7


def test_the_wait_says_which_attempt_comes_and_when(tmp_path, monkeypatch, caplog):
    answers = [
        urllib.error.HTTPError("http://x", 502, "bad gateway", {}, None),
        FakeResponse(b"<osm></osm>"),
    ]

    def fake_urlopen(req, timeout):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr(overpass.urllib.request, "urlopen", fake_urlopen)
    with caplog.at_level(logging.WARNING):
        overpass.fetch("q", tmp_path, url="http://x", sleep=lambda s: None)
    assert "HTTP 502; attempt 2/3 in 30 s" in caplog.text


def test_a_second_run_waits_for_the_first_and_takes_its_answer(tmp_path, monkeypatch):
    def fake_urlopen(req, timeout):
        raise AssertionError("the answer was already cached by the other run")

    monkeypatch.setattr(overpass.urllib.request, "urlopen", fake_urlopen)
    lock = (tmp_path / ".lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX)  # the other run, mid-request

    def other_run_finishes():
        time.sleep(0.2)
        (tmp_path / f"{overpass.cache_key('q')}.osm").write_text("<osm></osm>")
        lock.close()

    threading.Thread(target=other_run_finishes).start()
    path = overpass.fetch("q", tmp_path, url="http://x", sleep=lambda s: None)
    assert path.read_text() == "<osm></osm>"


def test_nothing_temporary_is_left_behind(tmp_path, monkeypatch):
    monkeypatch.setattr(
        overpass.urllib.request, "urlopen", lambda r, timeout: FakeResponse(b"<osm></osm>")
    )
    overpass.fetch("q", tmp_path, url="http://x", sleep=lambda s: None)
    assert not list(tmp_path.glob("*tmp*"))


def test_fetch_gives_up_on_other_errors(tmp_path, monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError("http://x", 400, "bad", {}, None)

    monkeypatch.setattr(overpass.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(overpass.OverpassError, match="400"):
        overpass.fetch("q", tmp_path, url="http://x", sleep=lambda s: None)


def test_runtime_error_in_a_200_is_an_error(tmp_path, monkeypatch):
    body = b"<osm><remark> runtime error: Query timed out </remark></osm>"
    monkeypatch.setattr(overpass.urllib.request, "urlopen", lambda r, timeout: FakeResponse(body))
    with pytest.raises(overpass.OverpassError):
        overpass.fetch("q", tmp_path, url="http://x", sleep=lambda s: None)
    assert not list(tmp_path.glob("*.osm"))  # nothing cached


class BrokenResponse(FakeResponse):
    def __init__(self, error):
        super().__init__(b"")
        self.error = error

    def read(self, *args):
        raise self.error


@pytest.mark.parametrize(
    "error, message",
    [
        (http.client.IncompleteRead(b"<osm>", 100), "cut the answer short"),
        (ConnectionResetError(), "cut the answer short"),
        (TimeoutError("timed out"), "did not answer"),
    ],
)
def test_errors_while_reading_are_overpass_errors(tmp_path, monkeypatch, error, message):
    monkeypatch.setattr(
        overpass.urllib.request, "urlopen", lambda r, timeout: BrokenResponse(error)
    )
    with pytest.raises(overpass.OverpassError, match=message):
        overpass.fetch("q", tmp_path, url="http://x", sleep=lambda s: None)
    assert not list(tmp_path.glob("*.osm"))


def test_retry_after_takes_seconds_or_an_http_date():
    assert overpass.retry_after("12", 30) == 12
    assert overpass.retry_after(None, 30) == 30
    assert overpass.retry_after("soon", 30) == 30
    in_a_minute = email.utils.formatdate(time.time() + 60, usegmt=True)
    assert 55 <= overpass.retry_after(in_a_minute, 30) <= 60
    assert overpass.retry_after(email.utils.formatdate(0, usegmt=True), 30) == 0


def test_a_box_is_rounded_outwards_to_the_grid():
    assert overpass.snap((42.8775, -8.5510, 42.8845, -8.5385)) == (42.87, -8.56, 42.89, -8.53)
    # On the grid already, it stays (no float slip one cell out).
    assert overpass.snap((42.88, -8.55, 42.89, -8.54)) == (42.88, -8.55, 42.89, -8.54)


@pytest.fixture
def downloads(monkeypatch):
    """The queries that reached the (fake) server."""
    asked = []

    def fake_urlopen(req, timeout):
        asked.append(urllib.parse.parse_qs(req.data.decode())["data"][0])
        return FakeResponse(b"<osm version='0.6'></osm>")

    monkeypatch.setattr(overpass.urllib.request, "urlopen", fake_urlopen)
    return asked


def _area(template, bounds, cache):
    return overpass.fetch_area(template, bounds, cache, url="http://x", sleep=lambda s: None)


T = f"[out:xml];way['highway']{overpass.BOX};out;"


def test_a_map_moved_a_little_asks_the_same_rounded_query(tmp_path, downloads):
    first = _area(T, (42.8775, -8.5510, 42.8845, -8.5385), tmp_path)
    moved = _area(T, (42.8771, -8.5502, 42.8841, -8.5377), tmp_path)
    assert first == moved
    assert downloads == ["[out:xml];way['highway'](42.87000,-8.56000,42.89000,-8.53000);out;"]


def test_an_answer_for_a_larger_area_serves_any_area_inside_it(tmp_path, downloads):
    large = _area(T, (42.80, -8.70, 43.00, -8.40), tmp_path)
    assert _area(T, (42.8775, -8.5510, 42.8845, -8.5385), tmp_path) == large
    assert len(downloads) == 1
    # Not another layer's query, nor an area that sticks out.
    _area(T.replace("highway", "building"), (42.8775, -8.5510, 42.8845, -8.5385), tmp_path)
    _area(T, (42.95, -8.50, 43.05, -8.45), tmp_path)
    assert len(downloads) == 3


def test_of_the_answers_that_cover_it_the_smallest_is_used(tmp_path, downloads):
    medium = _area(T, (42.85, -8.60, 42.90, -8.50), tmp_path)
    large = _area(T, (42.0, -9.0, 43.5, -8.0), tmp_path)  # holds the medium one: asked
    assert medium != large and len(downloads) == 2
    assert _area(T, (42.87, -8.56, 42.88, -8.54), tmp_path) == medium  # inside both
    assert len(downloads) == 2

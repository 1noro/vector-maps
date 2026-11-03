import email.utils
import http.client
import io
import time
import urllib.error

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

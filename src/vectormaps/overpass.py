"""Overpass client with an on-disk cache.

The public servers limit by IP, so: one request at a time, a cache keyed by the
exact query, and a wait (not a blind retry loop) when the server says no. "One
at a time" holds between processes too: two `make map` at once take turns
through a lock file in the cache.

A map asks by area (`fetch_area`), and two things make the cache serve more than
the exact same map (Nov 4): the box is rounded outwards to a grid, so a map moved a
little asks the same query; and an answer cached for a box that holds the new one
(the same layer, zoomed in, a smaller paper) is used instead of asking again.
"""

import contextlib
import email.utils
import fcntl
import hashlib
import http.client
import json
import logging
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from vectormaps.tmpfile import tmp_beside

log = logging.getLogger(__name__)

DEFAULT_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "vector-maps/0.1 (+https://github.com/1noro/vector-maps)"
RETRY_STATUS = {429, 502, 503, 504}
MAX_ATTEMPTS = 3
PAUSE_BETWEEN_REQUESTS = 1.0
TIMEOUT = 240  # seconds; the query itself asks the server for 180
BOX = "{{bbox}}"  # where a query template takes its (south,west,north,east)
GRID = 0.01  # degrees (~1 km): boxes are rounded outwards to it

Bounds = tuple[float, float, float, float]  # south, west, north, east


class OverpassError(RuntimeError):
    pass


def cache_key(query: str) -> str:
    return hashlib.sha1(query.encode()).hexdigest()[:16]


def bbox(bounds: Bounds) -> str:
    s, w, n, e = (f"{v:.5f}" for v in bounds)
    return f"({s},{w},{n},{e})"


def _to_grid(value: float, rounding) -> float:
    # round() first: 42.88 / 0.01 is 4287.999…, which floor would take one cell down.
    return round(rounding(round(value / GRID, 6)) * GRID, 5)


def snap(bounds: Bounds) -> Bounds:
    """The box rounded outwards to the grid: it always holds the one asked for."""
    s, w, n, e = bounds
    return (
        _to_grid(s, math.floor),
        _to_grid(w, math.floor),
        _to_grid(n, math.ceil),
        _to_grid(e, math.ceil),
    )


def _holds(outer: Bounds, inner: Bounds) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and (outer[3] >= inner[3])
    )


def _area_note(osm: Path) -> Path:
    """Beside each answer fetched by area: which template and box it answers."""
    return osm.with_name(f"{osm.stem}.area.json")


def _cached_area(template: str, bounds: Bounds, cache_dir: Path) -> Path | None:
    """The smallest cached answer to `template` whose box holds `bounds`, if any."""
    key = cache_key(template)
    best: tuple[float, Path] | None = None
    for note in cache_dir.glob("*.area.json"):
        try:
            data = json.loads(note.read_text(encoding="utf-8"))
            box = tuple(float(v) for v in data["bounds"])
        except (OSError, ValueError, KeyError, TypeError):
            continue  # a broken note only costs a download
        osm = note.with_name(note.name.removesuffix(".area.json") + ".osm")
        if data.get("template") != key or not _holds(box, bounds) or not osm.exists():
            continue
        size = (box[2] - box[0]) * (box[3] - box[1])
        if best is None or size < best[0]:
            best = (size, osm)
    return best[1] if best else None


def fetch_area(
    template: str, bounds: Bounds, cache_dir: Path, url: str | None = None, sleep=time.sleep
) -> Path:
    """The OSM XML for a query `template` (with BOX where the box goes) over `bounds`.

    It may cover more than `bounds`: the caller keeps what it needs.
    """
    cached = _cached_area(template, bounds, cache_dir)
    if cached is not None:
        log.info("cached: %s (covers this area)", cached.name)
        return cached
    box = snap(bounds)
    osm = fetch(template.replace(BOX, bbox(box)), cache_dir, url, sleep)
    note = _area_note(osm)
    if not note.exists():
        tmp = tmp_beside(note)
        try:
            tmp.write_text(json.dumps({"template": cache_key(template), "bounds": box}))
            tmp.replace(note)
        finally:
            tmp.unlink(missing_ok=True)
    return osm


def retry_after(value: str | None, default: int) -> int:
    """Seconds to wait from a Retry-After header, which is either seconds or an HTTP date."""
    if not value:
        return default
    value = value.strip()
    if value.isdigit():
        return int(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return default
    return max(0, round(when.timestamp() - time.time()))


@contextlib.contextmanager
def _one_at_a_time(cache_dir: Path):
    """Hold the cache's lock file: one Overpass request at a time, across processes too."""
    with (cache_dir / ".lock").open("a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log.info("another run is querying Overpass, waiting for it to finish")
            fcntl.flock(fh, fcntl.LOCK_EX)
        yield  # closing the file releases the lock


def fetch(query: str, cache_dir: Path, url: str | None = None, sleep=time.sleep) -> Path:
    """Return the path of the OSM XML for `query`, downloading it if not cached."""
    url = url or os.environ.get("OVERPASS_URL", DEFAULT_URL)
    path = cache_dir / f"{cache_key(query)}.osm"
    if path.exists():
        log.info("cached: %s", path.name)
        return path
    cache_dir.mkdir(parents=True, exist_ok=True)
    with _one_at_a_time(cache_dir):
        if path.exists():  # the other run asked the same while we waited
            log.info("cached: %s", path.name)
            return path
        data = _download(query, url, sleep)
        tmp = tmp_beside(path)
        try:
            tmp.write_bytes(data)
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)
        sleep(PAUSE_BETWEEN_REQUESTS)  # still holding the lock: the pause counts for everyone
    return path


def _download(query: str, url: str, sleep) -> bytes:
    body = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = resp.read()
            break
        except urllib.error.HTTPError as err:
            if err.code not in RETRY_STATUS or attempt == MAX_ATTEMPTS:
                raise OverpassError(f"Overpass answered HTTP {err.code}") from err
            header = err.headers.get("Retry-After") if err.headers else None
            wait = retry_after(header, 30 * attempt)
            # The spinner counts the whole layer, so say when the next attempt starts.
            log.warning(
                "Overpass answered HTTP %d; attempt %d/%d in %d s",
                err.code,
                attempt + 1,
                MAX_ATTEMPTS,
                wait,
            )
            sleep(wait)
        except urllib.error.URLError as err:
            raise OverpassError(f"cannot reach Overpass: {err.reason}") from err
        # Errors while reading the answer: not a "wait and retry" case (only 429/5xx are).
        except TimeoutError as err:
            raise OverpassError(
                f"Overpass did not answer within {TIMEOUT} s; try later or a smaller area"
            ) from err
        except (http.client.HTTPException, ConnectionError) as err:
            raise OverpassError(
                f"Overpass cut the answer short ({type(err).__name__}); try again later"
            ) from err

    text = data.decode("utf-8", "replace")
    if "<osm" not in text or "runtime error" in text:
        raise OverpassError("Overpass returned an error or a truncated answer; try a smaller area")
    return data

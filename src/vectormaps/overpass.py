"""Overpass client with an on-disk cache.

The public servers limit by IP, so: one request at a time, a cache keyed by the
exact query, and a wait (not a blind retry loop) when the server says no.
"""

import hashlib
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "vector-maps/0.1 (+https://github.com/1noro/vector-maps)"
RETRY_STATUS = {429, 502, 503, 504}
MAX_ATTEMPTS = 3
PAUSE_BETWEEN_REQUESTS = 1.0


class OverpassError(RuntimeError):
    pass


def cache_key(query: str) -> str:
    return hashlib.sha1(query.encode()).hexdigest()[:16]


def fetch(query: str, cache_dir: Path, url: str | None = None, sleep=time.sleep) -> Path:
    """Return the path of the OSM XML for `query`, downloading it if not cached."""
    url = url or os.environ.get("OVERPASS_URL", DEFAULT_URL)
    path = cache_dir / f"{cache_key(query)}.osm"
    if path.exists():
        log.info("cached: %s", path.name)
        return path
    cache_dir.mkdir(parents=True, exist_ok=True)

    body = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                data = resp.read()
            break
        except urllib.error.HTTPError as err:
            if err.code not in RETRY_STATUS or attempt == MAX_ATTEMPTS:
                raise OverpassError(f"Overpass answered HTTP {err.code}") from err
            wait = int(err.headers.get("Retry-After") or 30 * attempt)
            log.warning("Overpass answered HTTP %d, waiting %d s", err.code, wait)
            sleep(wait)
        except urllib.error.URLError as err:
            raise OverpassError(f"cannot reach Overpass: {err.reason}") from err

    text = data.decode("utf-8", "replace")
    if "<osm" not in text or "runtime error" in text:
        raise OverpassError("Overpass returned an error or a truncated answer; try a smaller area")
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.rename(path)
    sleep(PAUSE_BETWEEN_REQUESTS)
    return path

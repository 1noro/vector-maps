"""Download a PBF extract (e.g. from Geofabrik) into data/pbf. No account or key needed."""

import logging
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)

USER_AGENT = "vector-maps/0.1 (+https://github.com/1noro/vector-maps)"
CHUNK = 1 << 20
PBF_DIR = Path("data/pbf")  # where `make pbf` leaves the extracts


def download(url: str, out_dir: Path) -> Path:
    name = Path(urlparse(url).path).name
    if not name.endswith(".osm.pbf"):
        raise ValueError(f"expected a URL ending in .osm.pbf, got {url!r}")
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / name
    tmp = dest.with_name(name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp, tmp.open("wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        next_report = 0.1
        while chunk := resp.read(CHUNK):
            fh.write(chunk)
            done += len(chunk)
            if total and done / total >= next_report:
                log.info("%d%% of %d MiB", done * 100 // total, total >> 20)
                next_report += 0.1
    tmp.replace(dest)
    log.info("saved %s", dest)
    return dest

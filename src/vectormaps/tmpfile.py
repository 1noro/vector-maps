"""Names for the temporary file a result is written to before it takes its place.

Two `make map` at once may write the same cache file. Each one writes to its own
temporary name and then renames it, so neither reads the other's half-written
file. The PID is not enough: each run is its own container, and there Python is
always PID 1.
"""

import secrets
from pathlib import Path


def tmp_beside(path: Path) -> Path:
    """A fresh name next to `path` that keeps its extensions (GDAL, osmium and Inkscape read them).

    `abc.osm.pbf` -> `abc.3f9a1c2e.tmp.osm.pbf`.
    """
    base, dot, rest = path.name.partition(".")
    return path.with_name(f"{base}.{secrets.token_hex(4)}.tmp{dot}{rest}")

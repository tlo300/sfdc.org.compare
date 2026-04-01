"""Discovery module: queries the source org to find available metadata types and data objects."""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_SF_CMD = "sf.cmd" if sys.platform == "win32" else "sf"


def load_discovery_cache(cache_path: str) -> dict:
    """Return cached discovery result, or {} if the cache file does not exist."""
    path = Path(cache_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_discovery_cache(cache_path: str, data: dict) -> None:
    """Write discovery result to cache file (overwrites if present)."""
    Path(cache_path).write_text(json.dumps(data, indent=2))

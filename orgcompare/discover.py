"""Discovery module: queries the source org to find available metadata types and data objects."""
import json
from pathlib import Path


def load_discovery_cache(cache_path: str) -> dict:
    """Return cached discovery result, or {} if the cache file does not exist."""
    path = Path(cache_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_discovery_cache(cache_path: str, data: dict) -> None:
    """Write discovery result to cache file (overwrites if present)."""
    Path(cache_path).write_text(json.dumps(data, indent=2), encoding="utf-8")

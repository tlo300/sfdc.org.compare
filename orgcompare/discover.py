"""Discovery module: queries the source org to find available metadata types and data objects."""
import json
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# On Windows the sf CLI is a .cmd file; use sf.cmd so subprocess can find it
# without needing shell=True (which breaks argument passing on Windows).
_SF_CMD = "sf.cmd" if sys.platform == "win32" else "sf"


def load_discovery_cache(cache_path: str) -> dict:
    """Return cached discovery result, or {} if the cache file does not exist."""
    path = Path(cache_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_discovery_cache(cache_path: str, data: dict) -> None:
    """Write discovery result to cache file (overwrites if present)."""
    Path(cache_path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _list_all_metadata_types(org_alias: str) -> list[str]:
    """Return all registered metadata type names from the org registry."""
    result = subprocess.run(
        [_SF_CMD, "org", "list", "metadata-types", "--target-org", org_alias, "--json"],
        capture_output=True, encoding="utf-8", errors="replace", check=True,
    )
    data = json.loads(result.stdout)
    return [t["xmlName"] for t in data["result"]["metadataObjects"]]


def _type_has_content(org_alias: str, type_name: str) -> bool:
    """Return True if the org has at least one deployed component of this metadata type."""
    result = subprocess.run(
        [_SF_CMD, "org", "list", "metadata", "--metadata-type", type_name,
         "--target-org", org_alias, "--json"],
        capture_output=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout)
        components = data.get("result") or []
        return len(components) > 0
    except (json.JSONDecodeError, KeyError):
        return False


def discover_metadata_types(org_alias: str, max_workers: int = 10) -> list[str]:
    """Return sorted list of metadata type names that have at least one component in the org.

    Checks all registered types in parallel (max_workers threads).
    """
    all_types = _list_all_metadata_types(org_alias)
    found = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_type_has_content, org_alias, t): t for t in all_types}
        for future in as_completed(futures):
            if future.result():
                found.append(futures[future])
    return sorted(found)


def discover_data_objects(org_alias: str) -> list[str]:
    """Return sorted list of all queryable SObject API names from the org.

    Uses EntityDefinition SOQL — consistent with the existing data query pattern.
    """
    result = subprocess.run(
        [
            _SF_CMD, "data", "query",
            "--query",
            "SELECT QualifiedApiName FROM EntityDefinition WHERE IsQueryable = true ORDER BY QualifiedApiName",
            "--target-org", org_alias,
            "--result-format", "json",
        ],
        capture_output=True, encoding="utf-8", errors="replace", check=True,
    )
    data = json.loads(result.stdout)
    records = data.get("result", {}).get("records", [])
    return sorted([r["QualifiedApiName"] for r in records])


def run_discovery(org_alias: str, cache_path: str) -> dict:
    """Run full discovery against the org, save to cache, and return the result."""
    metadata_types = discover_metadata_types(org_alias)
    data_objects = discover_data_objects(org_alias)
    result = {"metadata_types": metadata_types, "data_objects": data_objects}
    save_discovery_cache(cache_path, result)
    return result

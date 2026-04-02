"""Discovery module: queries the source org to find available metadata types and data objects."""
import json
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

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


def _list_all_metadata_types(org_alias: str, emit=None) -> list[str]:
    """Return all registered metadata type names from the org registry."""
    if emit:
        emit("debug", f"{_SF_CMD} org list metadata-types --target-org {org_alias} --json")
    result = subprocess.run(
        [_SF_CMD, "org", "list", "metadata-types", "--target-org", org_alias, "--json"],
        capture_output=True, encoding="utf-8", errors="replace", check=True,
    )
    data = json.loads(result.stdout)
    types = [t["xmlName"] for t in data["result"]["metadataObjects"]]
    if emit:
        emit("normal", f"Found {len(types)} registered metadata types")
    return types


def _type_has_content(org_alias: str, type_name: str, emit=None) -> bool:
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
        has = len(components) > 0
        if emit and has:
            emit("debug", f"  {type_name}: {len(components)} component(s)")
        return has
    except (json.JSONDecodeError, KeyError):
        return False


def discover_metadata_types(org_alias: str, max_workers: int = 10, emit=None) -> list[str]:
    """Return sorted list of metadata type names that have at least one component in the org.

    Checks all registered types in parallel (max_workers threads).
    """
    if emit:
        emit("normal", "Listing all metadata types...")
    all_types = _list_all_metadata_types(org_alias, emit=emit)
    if emit:
        emit("normal", f"Checking {len(all_types)} types for content (parallel)...")
    found = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_type_has_content, org_alias, t, emit): t for t in all_types}
        for future in as_completed(futures):
            if future.result():
                found.append(futures[future])
    result = sorted(found)
    if emit:
        emit("normal", f"Found {len(result)} metadata types with content")
    return result


def discover_data_objects(org_alias: str, emit=None) -> list[str]:
    """Return sorted list of all queryable SObject API names from the org.

    EntityDefinition does not support queryMore(), so we paginate via LIMIT/OFFSET.
    """
    if emit:
        emit("normal", "Querying queryable data objects...")
    page_size = 500
    names: list[str] = []
    offset = 0
    page = 1
    while True:
        if emit:
            emit("debug", f"  Fetching page {page} (LIMIT {page_size} OFFSET {offset})")
        query = (
            f"SELECT QualifiedApiName FROM EntityDefinition "
            f"WHERE IsQueryable = true "
            f"ORDER BY QualifiedApiName "
            f"LIMIT {page_size} OFFSET {offset}"
        )
        result = subprocess.run(
            [
                _SF_CMD, "data", "query",
                "--query", query,
                "--target-org", org_alias,
                "--use-tooling-api",
                "--result-format", "json",
            ],
            capture_output=True, encoding="utf-8", errors="replace", check=True,
        )
        records = json.loads(result.stdout).get("result", {}).get("records", [])
        names.extend(r["QualifiedApiName"] for r in records)
        if emit:
            emit("debug", f"  Page {page}: {len(records)} objects")
        if len(records) < page_size:
            break
        offset += page_size
        page += 1
    result = sorted(names)
    if emit:
        emit("normal", f"Found {len(result)} queryable objects")
    return result


def run_discovery(org_alias: str, cache_path: str, emit=None) -> dict:
    """Run full discovery against the org, save to cache, and return the result."""
    if emit:
        emit("quiet", f"Starting discovery on {org_alias}...")
    metadata_types = discover_metadata_types(org_alias, emit=emit)
    data_objects = discover_data_objects(org_alias, emit=emit)
    result = {"metadata_types": metadata_types, "data_objects": data_objects}
    save_discovery_cache(cache_path, result)
    return result

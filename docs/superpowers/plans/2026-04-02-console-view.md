# Console View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real-time right-side console panel that streams log output from Discover and Compare operations via Server-Sent Events.

**Architecture:** Each pipeline function (`discover.py`, `retrieve.py`, `compare.py`) gains an optional `emit(level, msg)` callback. Two new SSE GET endpoints (`/api/discover/stream`, `/api/compare/stream`) run the pipeline in a background thread, collecting events in a `queue.Queue` and yielding them to the browser. The UI is split into two columns; the right column holds the console panel. The browser uses `EventSource` to receive events and append them to the console log, filtered client-side by a verbosity dropdown.

**Tech Stack:** Python 3.14, Flask (`stream_with_context`, `Response`), `queue.Queue`, `threading.Thread`, vanilla JS `EventSource`, `localStorage`

---

## File Map

| File | Change |
|------|--------|
| `orgcompare/discover.py` | Add `emit` param to `run_discovery`, `discover_metadata_types`, `_list_all_metadata_types`, `_type_has_content`, `discover_data_objects` |
| `orgcompare/retrieve.py` | Add `emit` param to `retrieve_metadata`, `retrieve_data` |
| `orgcompare/compare.py` | Add `emit` param to `compare_metadata`, `compare_data` |
| `orgcompare/server.py` | Add `/api/discover/stream` and `/api/compare/stream` SSE endpoints; add `queue` and `threading` imports |
| `templates/ui.html` | Two-column layout; console panel HTML + CSS; replace `runDiscover`/`runCompare` JS with EventSource versions; rewrite `showStatus` to route to console; remove `#status` div |
| `tests/test_discover.py` | Tests that `emit` is called with expected messages |
| `tests/test_retrieve.py` | Tests that `emit` is called with expected messages |
| `tests/test_compare.py` | Tests that `emit` is called with expected messages |
| `tests/test_server.py` | Tests for the two new SSE endpoints |

---

## Task 1: Add `emit` to `discover.py`

**Files:**
- Modify: `orgcompare/discover.py`
- Test: `tests/test_discover.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_discover.py`:

```python
def test_run_discovery_calls_emit_quiet_start_and_done(tmp_path):
    cache_path = str(tmp_path / "discovered.json")
    calls = []
    def emit(level, msg, **kw): calls.append((level, msg))
    with patch("orgcompare.discover.discover_metadata_types", return_value=["ApexClass"]), \
         patch("orgcompare.discover.discover_data_objects", return_value=["Account"]):
        from orgcompare.discover import run_discovery
        run_discovery("DEVRCA", cache_path, emit=emit)
    levels = [c[0] for c in calls]
    assert "quiet" in levels
    assert any("Starting" in msg for _, msg in calls)
    assert any("Done" in msg for _, msg in calls)


def test_run_discovery_without_emit_still_works(tmp_path):
    cache_path = str(tmp_path / "discovered.json")
    with patch("orgcompare.discover.discover_metadata_types", return_value=["Flow"]), \
         patch("orgcompare.discover.discover_data_objects", return_value=["Product2"]):
        from orgcompare.discover import run_discovery
        result = run_discovery("DEVRCA", cache_path)  # no emit param
    assert result["metadata_types"] == ["Flow"]


def test_discover_metadata_types_calls_emit_normal(tmp_path):
    calls = []
    def emit(level, msg, **kw): calls.append((level, msg))
    with patch("orgcompare.discover._list_all_metadata_types", return_value=["ApexClass", "Flow"]), \
         patch("orgcompare.discover._type_has_content", side_effect=lambda org, t, emit=None: t == "ApexClass"):
        from orgcompare.discover import discover_metadata_types
        discover_metadata_types("DEVRCA", emit=emit)
    assert any(level == "normal" for level, _ in calls)
    assert any("metadata type" in msg.lower() for _, msg in calls)


def test_discover_data_objects_calls_emit(tmp_path):
    calls = []
    def emit(level, msg, **kw): calls.append((level, msg))
    payload = json.dumps({"status": 0, "result": {"records": [{"QualifiedApiName": "Account"}]}})
    with patch("orgcompare.discover.subprocess.run", return_value=_mock_run(payload)):
        from orgcompare.discover import discover_data_objects
        discover_data_objects("DEVRCA", emit=emit)
    assert any("object" in msg.lower() or "queryable" in msg.lower() for _, msg in calls)
```

- [ ] **Step 2: Run tests to confirm they fail**

```
cd c:\Users\twanv\SalesforceProjects\OrgCompare
.venv/Scripts/python -m pytest tests/test_discover.py::test_run_discovery_calls_emit_quiet_start_and_done tests/test_discover.py::test_run_discovery_without_emit_still_works tests/test_discover.py::test_discover_metadata_types_calls_emit_normal tests/test_discover.py::test_discover_data_objects_calls_emit -v
```

Expected: FAIL (emit param not yet accepted)

- [ ] **Step 3: Update `discover.py` to accept emit callbacks**

Replace `orgcompare/discover.py` with:

```python
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
    """Return sorted list of metadata type names that have at least one component in the org."""
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
    """Return sorted list of all queryable SObject API names from the org."""
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
```

- [ ] **Step 4: Run new tests and full discover test suite**

```
.venv/Scripts/python -m pytest tests/test_discover.py -v
```

Expected: all 15 tests PASS

- [ ] **Step 5: Commit**

```bash
git add orgcompare/discover.py tests/test_discover.py
git commit -m "feat: add emit callback to discover.py pipeline functions"
```

---

## Task 2: Add `emit` to `retrieve.py`

**Files:**
- Modify: `orgcompare/retrieve.py`
- Test: `tests/test_retrieve.py`

- [ ] **Step 1: Write failing tests**

Read `tests/test_retrieve.py` first to understand existing patterns, then add:

```python
def test_retrieve_metadata_calls_emit_normal(tmp_path):
    calls = []
    def emit(level, msg, **kw): calls.append((level, msg))
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    with patch("orgcompare.retrieve.subprocess.run", return_value=mock_result):
        from orgcompare.retrieve import retrieve_metadata
        retrieve_metadata("DEVRCA", ["ApexClass", "Flow"], str(tmp_path), emit=emit)
    assert any("DEVRCA" in msg for _, msg in calls)
    assert any("2" in msg for _, msg in calls)  # 2 types


def test_retrieve_metadata_without_emit_still_works(tmp_path):
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    with patch("orgcompare.retrieve.subprocess.run", return_value=mock_result):
        from orgcompare.retrieve import retrieve_metadata
        retrieve_metadata("DEVRCA", ["ApexClass"], str(tmp_path))  # no emit


def test_retrieve_data_calls_emit_per_object(tmp_path):
    calls = []
    def emit(level, msg, **kw): calls.append((level, msg))
    payload = json.dumps({"status": 0, "result": {"records": [{"Id": "a", "Name": "Prod1"}, {"Id": "b", "Name": "Prod2"}]}})
    mock_result = MagicMock()
    mock_result.stdout = payload
    mock_result.returncode = 0
    with patch("orgcompare.retrieve.subprocess.run", return_value=mock_result):
        from orgcompare.retrieve import retrieve_data
        retrieve_data("DEVRCA", [{"name": "Product2", "query": "SELECT Id FROM Product2"}], str(tmp_path), emit=emit)
    assert any("Product2" in msg for _, msg in calls)
    assert any("2" in msg for _, msg in calls)  # 2 records
```

- [ ] **Step 2: Run tests to confirm they fail**

```
.venv/Scripts/python -m pytest tests/test_retrieve.py::test_retrieve_metadata_calls_emit_normal tests/test_retrieve.py::test_retrieve_metadata_without_emit_still_works tests/test_retrieve.py::test_retrieve_data_calls_emit_per_object -v
```

Expected: FAIL

- [ ] **Step 3: Update `retrieve.py`**

Replace `orgcompare/retrieve.py` with:

```python
import json
import subprocess
import sys
from pathlib import Path

_SF_CMD = "sf.cmd" if sys.platform == "win32" else "sf"


def retrieve_metadata(org_alias: str, metadata_types: list, output_dir: str, emit=None) -> None:
    """Retrieve metadata from org to output_dir using sf CLI."""
    if not metadata_types:
        return
    if emit:
        emit("normal", f"Retrieving metadata from {org_alias}... ({len(metadata_types)} types)")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    metadata_flags = []
    for t in metadata_types:
        metadata_flags += ["--metadata", t]
    cmd = (
        [_SF_CMD, "project", "retrieve", "start"]
        + metadata_flags
        + ["--target-org", org_alias, "--output-dir", str(output_path)]
    )
    if emit:
        emit("debug", f"  {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"sf project retrieve failed for {org_alias}:\n{result.stderr or result.stdout}"
        )
    if emit:
        emit("normal", f"  Metadata retrieved from {org_alias}")


def retrieve_data(org_alias: str, data_objects: list, output_dir: str, emit=None) -> None:
    """Query records from org and save each object as JSON."""
    if emit:
        emit("normal", f"Retrieving data from {org_alias}... ({len(data_objects)} objects)")
    data_path = Path(output_dir) / "data"
    data_path.mkdir(parents=True, exist_ok=True)
    for obj in data_objects:
        cmd = [
            _SF_CMD, "data", "query",
            "--query", obj["query"],
            "--target-org", org_alias,
            "--result-format", "json",
        ]
        if emit:
            emit("debug", f"  {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        data = json.loads(result.stdout)
        records = data.get("result", {}).get("records", [])
        out_file = data_path / f"{obj['name']}.json"
        out_file.write_text(json.dumps(records, indent=2))
        if emit:
            emit("normal", f"  {obj['name']}: {len(records)} records")
```

- [ ] **Step 4: Run full retrieve test suite**

```
.venv/Scripts/python -m pytest tests/test_retrieve.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add orgcompare/retrieve.py tests/test_retrieve.py
git commit -m "feat: add emit callback to retrieve.py pipeline functions"
```

---

## Task 3: Add `emit` to `compare.py`

**Files:**
- Modify: `orgcompare/compare.py`
- Test: `tests/test_compare.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_compare.py`:

```python
def test_compare_metadata_calls_emit(tmp_path):
    calls = []
    def emit(level, msg, **kw): calls.append((level, msg))
    src = tmp_path / "src"
    tgt = tmp_path / "tgt"
    src.mkdir(); tgt.mkdir()
    (src / "classes").mkdir()
    (src / "classes" / "MyClass.cls-meta.xml").write_text("<ApexClass><apiVersion>58.0</apiVersion></ApexClass>")
    from orgcompare.compare import compare_metadata
    compare_metadata(str(src), str(tgt), emit=emit)
    assert any("Comparing metadata" in msg for _, msg in calls)
    assert any("added" in msg or "modified" in msg or "removed" in msg for _, msg in calls)


def test_compare_metadata_without_emit_still_works(tmp_path):
    src = tmp_path / "src"
    tgt = tmp_path / "tgt"
    src.mkdir(); tgt.mkdir()
    from orgcompare.compare import compare_metadata
    results = compare_metadata(str(src), str(tgt))  # no emit
    assert results == []


def test_compare_data_calls_emit_per_object(tmp_path):
    calls = []
    def emit(level, msg, **kw): calls.append((level, msg))
    src = tmp_path / "src" / "data"
    tgt = tmp_path / "tgt" / "data"
    src.mkdir(parents=True); tgt.mkdir(parents=True)
    (src / "Product2.json").write_text('[{"Name": "P1", "Id": "001"}]')
    (tgt / "Product2.json").write_text('[]')
    from orgcompare.compare import compare_data
    compare_data(str(tmp_path / "src"), str(tmp_path / "tgt"),
                 [{"name": "Product2", "external_id": "Name"}], emit=emit)
    assert any("Comparing data" in msg for _, msg in calls)
    assert any("Product2" in msg for _, msg in calls)


def test_compare_data_without_emit_still_works(tmp_path):
    src = tmp_path / "src" / "data"
    tgt = tmp_path / "tgt" / "data"
    src.mkdir(parents=True); tgt.mkdir(parents=True)
    (src / "Product2.json").write_text('[]')
    (tgt / "Product2.json").write_text('[]')
    from orgcompare.compare import compare_data
    results = compare_data(str(tmp_path / "src"), str(tmp_path / "tgt"),
                           [{"name": "Product2", "external_id": "Name"}])  # no emit
    assert results == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```
.venv/Scripts/python -m pytest tests/test_compare.py::test_compare_metadata_calls_emit tests/test_compare.py::test_compare_metadata_without_emit_still_works tests/test_compare.py::test_compare_data_calls_emit_per_object tests/test_compare.py::test_compare_data_without_emit_still_works -v
```

Expected: FAIL

- [ ] **Step 3: Update `compare.py`**

In `compare_metadata`, add `emit=None` parameter and emit calls:

```python
def compare_metadata(
    source_dir: str, target_dir: str, metadata_types: list | None = None, emit=None
) -> List[DiffResult]:
    """Compare metadata XML files between source and target directories."""
    if emit:
        emit("normal", "Comparing metadata...")
    source_path = Path(source_dir)
    target_path = Path(target_dir)

    source_files = {
        f.relative_to(source_path): f
        for f in source_path.rglob("*-meta.xml")
    }
    target_files = {
        f.relative_to(target_path): f
        for f in target_path.rglob("*-meta.xml")
    }

    source_label = Path(source_dir).name
    target_label = Path(target_dir).name

    results = []
    for rel_path in sorted(set(source_files) | set(target_files)):
        type_name = _infer_type(rel_path)
        if metadata_types is not None and type_name not in metadata_types:
            continue
        name = _clean_name(rel_path)
        in_source = rel_path in source_files
        in_target = rel_path in target_files

        if in_source and not in_target:
            source_val = _xml_to_dict(source_files[rel_path])
            source_lines = source_files[rel_path].read_text(encoding="utf-8").splitlines(keepends=True)
            xml_diff = "".join(difflib.unified_diff(
                [], source_lines, fromfile="/dev/null", tofile=source_label,
            ))
            results.append(DiffResult(
                category="metadata", type=type_name, name=name,
                status="added", source_value=source_val, target_value={}, diff={},
                xml_diff=xml_diff,
            ))
        elif not in_source and in_target:
            target_val = _xml_to_dict(target_files[rel_path])
            target_lines = target_files[rel_path].read_text(encoding="utf-8").splitlines(keepends=True)
            xml_diff = "".join(difflib.unified_diff(
                target_lines, [], fromfile=target_label, tofile="/dev/null",
            ))
            results.append(DiffResult(
                category="metadata", type=type_name, name=name,
                status="removed", source_value={}, target_value=target_val, diff={},
                xml_diff=xml_diff,
            ))
        else:
            source_val = _xml_to_dict(source_files[rel_path])
            target_val = _xml_to_dict(target_files[rel_path])
            ddiff = DeepDiff(target_val, source_val, ignore_order=True)
            diff_dict = json.loads(ddiff.to_json()) if ddiff else {}
            status = "modified" if diff_dict else "identical"
            if status == "modified":
                source_lines = source_files[rel_path].read_text(encoding="utf-8").splitlines(keepends=True)
                target_lines = target_files[rel_path].read_text(encoding="utf-8").splitlines(keepends=True)
                xml_diff = "".join(difflib.unified_diff(
                    source_lines, target_lines, fromfile=source_label, tofile=target_label,
                ))
            else:
                xml_diff = None
            results.append(DiffResult(
                category="metadata", type=type_name, name=name,
                status=status, source_value=source_val, target_value=target_val, diff=diff_dict,
                xml_diff=xml_diff,
            ))

    if emit:
        added = sum(1 for r in results if r.status == "added")
        modified = sum(1 for r in results if r.status == "modified")
        removed = sum(1 for r in results if r.status == "removed")
        identical = sum(1 for r in results if r.status == "identical")
        emit("normal", f"  Metadata: {added} added, {modified} modified, {removed} removed, {identical} identical")

    return results
```

In `compare_data`, add `emit=None` parameter and emit calls:

```python
def compare_data(source_dir: str, target_dir: str, data_objects: list, emit=None) -> List[DiffResult]:
    """Compare data records between source and target. Matches by external_id field."""
    if emit:
        emit("normal", "Comparing data...")
    results = []

    for obj_config in data_objects:
        obj_name = obj_config["name"]
        external_id = obj_config.get("external_id", "Name")

        source_file = Path(source_dir) / "data" / f"{obj_name}.json"
        target_file = Path(target_dir) / "data" / f"{obj_name}.json"

        source_records = json.loads(source_file.read_text()) if source_file.exists() else []
        target_records = json.loads(target_file.read_text()) if target_file.exists() else []

        def to_indexed(records: list) -> dict:
            return {
                str(r[external_id]): {k: v for k, v in r.items() if k != "attributes"}
                for r in records
                if external_id in r
            }

        source_indexed = to_indexed(source_records)
        target_indexed = to_indexed(target_records)
        source_keys = set(source_indexed)
        target_keys = set(target_indexed)

        obj_start = len(results)

        for key in sorted(source_keys - target_keys):
            results.append(DiffResult(
                category="data", type=obj_name, name=key,
                status="added", source_value=source_indexed[key], target_value={}, diff={},
            ))

        for key in sorted(target_keys - source_keys):
            results.append(DiffResult(
                category="data", type=obj_name, name=key,
                status="removed", source_value={}, target_value=target_indexed[key], diff={},
            ))

        for key in sorted(source_keys & target_keys):
            src = {k: v for k, v in source_indexed[key].items() if k != "Id"}
            tgt = {k: v for k, v in target_indexed[key].items() if k != "Id"}
            ddiff = DeepDiff(tgt, src, ignore_order=True)
            diff_dict = json.loads(ddiff.to_json()) if ddiff else {}
            status = "modified" if diff_dict else "identical"
            results.append(DiffResult(
                category="data", type=obj_name, name=key,
                status=status, source_value=source_indexed[key],
                target_value=target_indexed[key], diff=diff_dict,
            ))

        if emit:
            non_identical = sum(1 for r in results[obj_start:] if r.status != "identical")
            emit("normal", f"  {obj_name}: {non_identical} difference(s)")

    return results
```

- [ ] **Step 4: Run full compare test suite**

```
.venv/Scripts/python -m pytest tests/test_compare.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add orgcompare/compare.py tests/test_compare.py
git commit -m "feat: add emit callback to compare.py pipeline functions"
```

---

## Task 4: Add SSE streaming endpoints to `server.py`

**Files:**
- Modify: `orgcompare/server.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_server.py`:

```python
def test_discover_stream_returns_done_event(client):
    def fake_discovery(org, cache_path, emit=None):
        if emit:
            emit("normal", "test normal message")
        return {"metadata_types": ["ApexClass"], "data_objects": ["Account"]}

    with patch("orgcompare.server.run_discovery", side_effect=fake_discovery), \
         patch("orgcompare.server._load_orgs", return_value={
             "selection": {"source": "DEVRCA", "target": "UATR"}, "orgs": []
         }):
        res = client.get("/api/discover/stream")
        body = res.get_data(as_text=True)
    assert res.status_code == 200
    assert "text/event-stream" in res.content_type
    assert '"done": true' in body or '"done":true' in body
    assert "ApexClass" in body


def test_discover_stream_emits_intermediate_message(client):
    def fake_discovery(org, cache_path, emit=None):
        if emit:
            emit("normal", "Listing all metadata types...")
        return {"metadata_types": [], "data_objects": []}

    with patch("orgcompare.server.run_discovery", side_effect=fake_discovery), \
         patch("orgcompare.server._load_orgs", return_value={
             "selection": {"source": "DEVRCA", "target": "UATR"}, "orgs": []
         }):
        res = client.get("/api/discover/stream")
        body = res.get_data(as_text=True)
    assert "Listing all metadata types" in body


def test_discover_stream_emits_error_event_on_exception(client):
    with patch("orgcompare.server.run_discovery", side_effect=RuntimeError("sf failed")), \
         patch("orgcompare.server._load_orgs", return_value={
             "selection": {"source": "DEVRCA", "target": "UATR"}, "orgs": []
         }):
        res = client.get("/api/discover/stream")
        body = res.get_data(as_text=True)
    assert '"error"' in body
    assert "sf failed" in body


def test_compare_stream_returns_done_event(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "source_org: DEVRCA\ntarget_org: UATR\n"
        "metadata_types: [ApexClass]\n"
        "data_objects:\n  - name: Product2\n    query: SELECT Id FROM Product2\n    external_id: Name\n"
    )
    with patch("orgcompare.server.retrieve_metadata"), \
         patch("orgcompare.server.retrieve_data"), \
         patch("orgcompare.server.compare_metadata", return_value=[]), \
         patch("orgcompare.server.compare_data", return_value=[]), \
         patch("orgcompare.server.save_results"), \
         patch("orgcompare.server._load_orgs", return_value={
             "selection": {"source": "DEVRCA", "target": "UATR"}, "orgs": []
         }):
        params = "metadata_types=%5B%22ApexClass%22%5D&data_objects=%5B%22Product2%22%5D"
        res = client.get(f"/api/compare/stream?{params}")
        body = res.get_data(as_text=True)
    assert res.status_code == 200
    assert "text/event-stream" in res.content_type
    assert '"done": true' in body or '"done":true' in body


def test_compare_stream_emits_error_on_exception(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "source_org: DEVRCA\ntarget_org: UATR\n"
        "metadata_types: [ApexClass]\ndata_objects: []\n"
    )
    with patch("orgcompare.server.retrieve_metadata", side_effect=RuntimeError("retrieve failed")), \
         patch("orgcompare.server._load_orgs", return_value={
             "selection": {"source": "DEVRCA", "target": "UATR"}, "orgs": []
         }):
        res = client.get("/api/compare/stream?metadata_types=%5B%22ApexClass%22%5D&data_objects=%5B%5D")
        body = res.get_data(as_text=True)
    assert '"error"' in body
    assert "retrieve failed" in body
```

- [ ] **Step 2: Run tests to confirm they fail**

```
.venv/Scripts/python -m pytest tests/test_server.py::test_discover_stream_returns_done_event tests/test_server.py::test_discover_stream_emits_intermediate_message tests/test_server.py::test_discover_stream_emits_error_event_on_exception tests/test_server.py::test_compare_stream_returns_done_event tests/test_server.py::test_compare_stream_emits_error_on_exception -v
```

Expected: FAIL (endpoints don't exist yet)

- [ ] **Step 3: Add SSE endpoints to `server.py`**

Add these imports at the top of `orgcompare/server.py` (after existing imports):

```python
import queue
from flask import Flask, jsonify, render_template, request, Response
from flask import stream_with_context
```

(Replace the existing `from flask import Flask, jsonify, render_template, request` line with the above two lines.)

Then add these two endpoints after the existing `post_discover` route and before the `run` function:

```python
@app.route("/api/discover/stream")
def discover_stream():
    orgs_data = _load_orgs()
    source = orgs_data["selection"]["source"]
    q = queue.Queue()

    def emit(level, msg, **extra):
        q.put({"level": level, "msg": msg, **extra})

    def worker():
        try:
            result = run_discovery(source, DISCOVERY_FILE, emit=emit)
            q.put({
                "level": "quiet",
                "msg": f"Done — {len(result['metadata_types'])} metadata types, {len(result['data_objects'])} objects",
                "done": True,
                **result,
            })
        except Exception as e:
            q.put({"level": "error", "msg": str(e), "done": True})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def generate():
        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.route("/api/compare/stream")
def compare_stream():
    config = _load_config()
    orgs_data = _load_orgs()
    source = orgs_data["selection"]["source"]
    target = orgs_data["selection"]["target"]

    raw_meta = request.args.get("metadata_types")
    raw_objs = request.args.get("data_objects")

    metadata_types = json.loads(raw_meta) if raw_meta is not None else config["metadata_types"]

    if raw_objs is not None:
        obj_names = json.loads(raw_objs)
        known = {o["name"]: o for o in config["data_objects"]}
        data_objects = [
            known[name] if name in known
            else {"name": name, "query": f"SELECT FIELDS(ALL) FROM {name} LIMIT 200", "external_id": "Id"}
            for name in obj_names
        ]
    else:
        data_objects = config["data_objects"]

    q = queue.Queue()

    def emit(level, msg, **extra):
        q.put({"level": level, "msg": msg, **extra})

    def worker():
        try:
            emit("quiet", f"Starting compare: {source} \u2192 {target}...")
            retrieve_metadata(source, metadata_types, f"output/retrieved/{source}", emit=emit)
            retrieve_metadata(target, metadata_types, f"output/retrieved/{target}", emit=emit)
            retrieve_data(source, data_objects, f"output/retrieved/{source}", emit=emit)
            retrieve_data(target, data_objects, f"output/retrieved/{target}", emit=emit)
            meta_diffs = compare_metadata(
                f"output/retrieved/{source}",
                f"output/retrieved/{target}",
                metadata_types=metadata_types,
                emit=emit,
            )
            data_diffs = compare_data(
                f"output/retrieved/{source}",
                f"output/retrieved/{target}",
                data_objects,
                emit=emit,
            )
            all_diffs = meta_diffs + data_diffs
            save_results(all_diffs, DIFF_FILE)
            q.put({
                "level": "quiet",
                "msg": f"Done \u2014 {len(all_diffs)} differences found",
                "done": True,
                "total": len(all_diffs),
            })
        except Exception as e:
            q.put({"level": "error", "msg": str(e), "done": True})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def generate():
        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
```

Also add `import json` to the top of `server.py` if not already present (it isn't — json is used via the pipeline modules, but now the server itself needs it for the SSE serialization). Add `import json` after the existing imports.

- [ ] **Step 4: Run full server test suite**

```
.venv/Scripts/python -m pytest tests/test_server.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add orgcompare/server.py tests/test_server.py
git commit -m "feat: add SSE streaming endpoints /api/discover/stream and /api/compare/stream"
```

---

## Task 5: Update `ui.html` — layout, console panel, EventSource wiring

**Files:**
- Modify: `templates/ui.html`

No unit tests for HTML/JS. Manual verification steps are listed at the end.

- [ ] **Step 1: Add console CSS to the `<style>` block**

In `templates/ui.html`, find the closing `</style>` tag (line 83) and insert before it:

```css
    /* Two-column layout */
    .main-layout { display: flex; gap: 16px; align-items: flex-start; }
    .main-col { flex: 1 1 0; min-width: 0; }
    .console-col { width: 340px; flex-shrink: 0; }
    @media (max-width: 900px) { .main-layout { flex-direction: column; } .console-col { width: 100%; } }

    /* Console panel */
    .console-panel { background: #1e1e1e; border-radius: 4px; overflow: hidden; }
    .console-header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: #2d2d2d; }
    .console-title { color: #ccc; font-weight: bold; font-size: 13px; flex: 1; font-family: monospace; }
    .console-header select { background: #3c3c3c; color: #ccc; border: 1px solid #555; border-radius: 3px; padding: 2px 6px; font-size: 12px; }
    .console-header .btn-secondary { padding: 3px 10px; font-size: 12px; background: #3c3c3c; border: 1px solid #555; color: #ccc; border-radius: 3px; }
    .console-log { font-family: monospace; font-size: 12px; padding: 10px 12px; height: 420px; overflow-y: auto; }
    .console-line { margin: 2px 0; white-space: pre-wrap; word-break: break-all; line-height: 1.5; }
    .console-line[data-level="quiet"] { color: #27ae60; }
    .console-line[data-level="normal"] { color: #ddd; }
    .console-line[data-level="debug"] { color: #555; }
    .console-line[data-level="error"] { color: #e74c3c; }
    .console-log.verbosity-quiet .console-line[data-level="normal"],
    .console-log.verbosity-quiet .console-line[data-level="debug"] { display: none; }
    .console-log.verbosity-normal .console-line[data-level="debug"] { display: none; }
```

- [ ] **Step 2: Wrap body content in two-column layout**

In `templates/ui.html`, find `<div id="status"></div>` and the `<!-- Tabs -->` comment. The structure from `<div id="status">` through the end of the Data tab (closing `</div>` before `<!-- Manage Orgs Modal -->`) needs to be wrapped.

Replace this block:

```html
  <div id="status"></div>

  <!-- Tabs -->
```

With:

```html
  <div class="main-layout">
  <div class="main-col">

  <!-- Tabs -->
```

Then find `</div>` that closes the Data tab (the `</div>` just before `<!-- Manage Orgs Modal -->`):

```html
  </div>

  <!-- Manage Orgs Modal -->
```

Replace it with:

```html
  </div>
  </div><!-- end main-col -->

  <!-- Console Panel -->
  <div class="console-col">
    <div class="console-panel">
      <div class="console-header">
        <span class="console-title">Console</span>
        <select id="console-verbosity" onchange="onVerbosityChange()">
          <option value="debug">Debug</option>
          <option value="normal" selected>Normal</option>
          <option value="quiet">Quiet</option>
        </select>
        <button class="btn-secondary" onclick="clearConsole()">Clear</button>
      </div>
      <div id="console-log" class="console-log verbosity-normal"></div>
    </div>
  </div>
  </div><!-- end main-layout -->

  <!-- Manage Orgs Modal -->
```

- [ ] **Step 3: Replace the `runDiscover`, `runCompare`, and `showStatus` JS functions**

Find and replace the entire `runDiscover` function:

```javascript
    async function runDiscover() {
      const btn = document.getElementById('discover-btn');
      btn.disabled = true;
      showStatus('Discovering — querying source org for metadata types and objects. This may take a minute...');
      try {
        const res = await fetch('/api/discover', { method: 'POST' });
        const data = await res.json();
        if (res.ok && !data.status) {
          renderDiscoveryResults(data);
          showStatus(`Discovery complete: ${(data.metadata_types || []).length} metadata types, ${(data.data_objects || []).length} objects.`);
        } else {
          showStatus(`Error: ${data.message || 'Unknown error'}`, false);
        }
      } catch (e) {
        showStatus(`Error: ${e.message}`, false);
      } finally {
        btn.disabled = false;
      }
    }
```

With:

```javascript
    function runDiscover() {
      const btn = document.getElementById('discover-btn');
      btn.disabled = true;
      _closeStream();
      clearConsole();
      _activeStream = new EventSource('/api/discover/stream');
      _activeStream.onmessage = (e) => {
        const data = JSON.parse(e.data);
        appendConsoleLine(data.level, data.msg);
        if (data.done) {
          _closeStream();
          if (data.level !== 'error') renderDiscoveryResults(data);
          btn.disabled = false;
        }
      };
      _activeStream.onerror = () => {
        appendConsoleLine('error', 'Connection error. Is the server running?');
        _closeStream();
        btn.disabled = false;
      };
    }
```

Find and replace the entire `runCompare` function:

```javascript
    async function runCompare() {
      const btn = document.getElementById('run-btn');
      btn.disabled = true;
      const selection = getSelection();
      if (!selection.metadata_types.length && !selection.data_objects.length) {
        showStatus('Select at least one metadata type or data object before running.', false);
        btn.disabled = false;
        return;
      }
      showStatus('Running compare — this may take a minute...');
      try {
        const res = await fetch('/api/run-compare', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(selection),
        });
        const data = await res.json();
        if (data.status === 'ok') {
          showStatus(`Compare complete: ${data.total} items.`);
          await fetchAndRenderResults();
        } else {
          showStatus(`Error: ${data.message}`, false);
        }
      } catch (e) {
        showStatus(`Error: ${e.message}`, false);
      } finally {
        btn.disabled = false;
      }
    }
```

With:

```javascript
    function runCompare() {
      const btn = document.getElementById('run-btn');
      btn.disabled = true;
      const selection = getSelection();
      if (!selection.metadata_types.length && !selection.data_objects.length) {
        appendConsoleLine('error', 'Select at least one metadata type or data object before running.');
        btn.disabled = false;
        return;
      }
      _closeStream();
      clearConsole();
      const params = new URLSearchParams({
        metadata_types: JSON.stringify(selection.metadata_types),
        data_objects: JSON.stringify(selection.data_objects),
      });
      _activeStream = new EventSource(`/api/compare/stream?${params}`);
      _activeStream.onmessage = (e) => {
        const data = JSON.parse(e.data);
        appendConsoleLine(data.level, data.msg);
        if (data.done) {
          _closeStream();
          if (data.level !== 'error') fetchAndRenderResults();
          btn.disabled = false;
        }
      };
      _activeStream.onerror = () => {
        appendConsoleLine('error', 'Connection error. Is the server running?');
        _closeStream();
        btn.disabled = false;
      };
    }
```

Find and replace the `showStatus` function:

```javascript
    function showStatus(msg, ok = true) {
      const el = document.getElementById('status');
      el.style.display = 'block';
      el.className = ok ? 'status-ok' : 'status-error';
      el.textContent = msg;
    }
```

With:

```javascript
    function showStatus(msg, ok = true) {
      appendConsoleLine(ok ? 'quiet' : 'error', msg);
    }
```

- [ ] **Step 4: Add console JS functions and init call**

Find the `// --- Init ---` comment and the lines below it:

```javascript
    // --- Init ---
    loadOrgsIntoDropdowns();
    loadProfilesIntoDropdown();
    // Clear any browser-restored checkbox state
    document.querySelectorAll('.meta-check, .obj-check').forEach(cb => { cb.checked = false; });
```

Replace with:

```javascript
    // --- Console ---
    let _activeStream = null;

    function _closeStream() {
      if (_activeStream) { _activeStream.close(); _activeStream = null; }
    }

    function clearConsole() {
      document.getElementById('console-log').innerHTML = '';
    }

    function appendConsoleLine(level, msg) {
      const log = document.getElementById('console-log');
      const line = document.createElement('div');
      line.className = 'console-line';
      line.dataset.level = level;
      line.textContent = msg;
      log.appendChild(line);
      log.scrollTop = log.scrollHeight;
    }

    function onVerbosityChange() {
      const val = document.getElementById('console-verbosity').value;
      localStorage.setItem('orgcompare_console_verbosity', val);
      const log = document.getElementById('console-log');
      log.classList.remove('verbosity-quiet', 'verbosity-normal', 'verbosity-debug');
      log.classList.add(`verbosity-${val}`);
    }

    function _initConsole() {
      const saved = localStorage.getItem('orgcompare_console_verbosity') || 'normal';
      document.getElementById('console-verbosity').value = saved;
      const log = document.getElementById('console-log');
      log.classList.remove('verbosity-quiet', 'verbosity-normal', 'verbosity-debug');
      log.classList.add(`verbosity-${saved}`);
    }

    // --- Init ---
    loadOrgsIntoDropdowns();
    loadProfilesIntoDropdown();
    _initConsole();
    // Clear any browser-restored checkbox state
    document.querySelectorAll('.meta-check, .obj-check').forEach(cb => { cb.checked = false; });
```

- [ ] **Step 5: Run the full test suite to confirm nothing broke**

```
.venv/Scripts/python -m pytest -v
```

Expected: all 107 (+ new) tests PASS

- [ ] **Step 6: Smoke test in browser**

Start the server:
```
.venv/Scripts/python -c "from orgcompare.server import app; app.run(port=5001, debug=False)"
```

Open `http://localhost:5001` and verify:
1. Console panel visible on the right side, dark background, "Console" label, verbosity dropdown, Clear button
2. Click "Discover source org" → console clears, lines appear in real-time as discovery runs
3. Green milestone lines at start/end, white normal lines, grey debug lines hidden at Normal verbosity
4. Switch dropdown to Debug → grey debug lines become visible immediately (no page reload)
5. Switch dropdown to Quiet → only green lines visible
6. After discover, click "Run Compare" → console clears, new lines stream in
7. Deploy buttons still show status in console via `showStatus`

- [ ] **Step 7: Commit**

```bash
git add templates/ui.html
git commit -m "feat: add real-time console panel with SSE streaming and verbosity control"
```

---

## Self-Review Notes

- All 5 spec requirements covered: right-side panel (Task 5), verbosity dropdown with localStorage (Task 5), auto-clear on new run (Task 5 — `clearConsole()` called at start of each operation), real-time streaming (Tasks 4+5), SSE with emit callback (Tasks 1–4).
- `showStatus` is rewritten to route to console — deploy feedback continues to work.
- `_activeStream` is module-level so clicking Discover mid-Compare cancels the previous stream cleanly.
- The `#status` div is removed from HTML; its CSS classes (`.status-ok`, `.status-error`) are now unused but harmless to leave in the stylesheet.
- The existing `POST /api/discover` and `POST /api/run-compare` endpoints are untouched — external callers are unaffected.

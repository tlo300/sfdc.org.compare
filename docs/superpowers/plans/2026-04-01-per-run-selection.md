# Per-Run Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-run selection of metadata types and data objects via named profiles, CLI flags, and a web UI selection panel.

**Architecture:** New `orgcompare/profiles.py` handles profile CRUD against `profiles.yaml`. `main.py` migrates from `sys.argv` to `argparse` and resolves the effective selection before passing filtered lists to existing retrieve/compare functions (no signature changes there). `compare_metadata` gains an optional filter. `server.py` gets three new profile endpoints and the run-compare endpoint learns to accept a selection. `ui.html` gets a pre-run selection panel.

**Tech Stack:** Python 3.14, PyYAML, argparse, Flask, Jinja2

---

## File Map

| File | Change |
|---|---|
| `profiles.yaml` | New — profile storage, created empty on first load |
| `orgcompare/profiles.py` | New — load/save/delete/validate profiles |
| `tests/test_profiles.py` | New — unit tests for profiles module |
| `orgcompare/compare.py` | Modify — add optional `metadata_types` filter to `compare_metadata` |
| `tests/test_compare.py` | Modify — add test for the new filter |
| `main.py` | Modify — migrate to argparse, add `--profile`/`--metadata`/`--objects` flags |
| `orgcompare/server.py` | Modify — 3 new profile endpoints, extend run-compare and GET / |
| `templates/ui.html` | Modify — pre-run selection panel with profile dropdown + checkboxes |

---

## Task 1: `orgcompare/profiles.py` and `tests/test_profiles.py`

**Files:**
- Create: `orgcompare/profiles.py`
- Create: `tests/test_profiles.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_profiles.py`:

```python
import pytest
import yaml
from orgcompare.profiles import load_profiles, save_profile, delete_profile, validate_profile

CONFIG = {
    "metadata_types": ["ApexClass", "Flow", "PermissionSet"],
    "data_objects": [
        {"name": "Product2", "query": "SELECT Id FROM Product2", "external_id": "Name"},
        {"name": "Pricebook2", "query": "SELECT Id FROM Pricebook2", "external_id": "Name"},
    ],
}


def test_load_profiles_creates_file_if_absent(tmp_path):
    path = str(tmp_path / "profiles.yaml")
    result = load_profiles(path)
    assert result == {}
    assert (tmp_path / "profiles.yaml").exists()


def test_save_and_load_profile(tmp_path):
    path = str(tmp_path / "profiles.yaml")
    save_profile(path, "quick", ["ApexClass"], ["Product2"])
    profiles = load_profiles(path)
    assert profiles["quick"] == {"metadata_types": ["ApexClass"], "data_objects": ["Product2"]}


def test_save_overwrites_existing_profile(tmp_path):
    path = str(tmp_path / "profiles.yaml")
    save_profile(path, "quick", ["ApexClass"], ["Product2"])
    save_profile(path, "quick", ["Flow"], ["Pricebook2"])
    profiles = load_profiles(path)
    assert profiles["quick"]["metadata_types"] == ["Flow"]


def test_delete_profile(tmp_path):
    path = str(tmp_path / "profiles.yaml")
    save_profile(path, "quick", ["ApexClass"], ["Product2"])
    delete_profile(path, "quick")
    profiles = load_profiles(path)
    assert "quick" not in profiles


def test_delete_nonexistent_profile_is_noop(tmp_path):
    path = str(tmp_path / "profiles.yaml")
    delete_profile(path, "does-not-exist")  # should not raise


def test_validate_profile_passes_for_valid_profile():
    profile = {"metadata_types": ["ApexClass"], "data_objects": ["Product2"]}
    validate_profile(profile, CONFIG)  # should not raise


def test_validate_profile_raises_for_unknown_metadata_type():
    profile = {"metadata_types": ["UnknownType"], "data_objects": ["Product2"]}
    with pytest.raises(ValueError, match="Unknown metadata types"):
        validate_profile(profile, CONFIG)


def test_validate_profile_raises_for_unknown_data_object():
    profile = {"metadata_types": ["ApexClass"], "data_objects": ["UnknownObject"]}
    with pytest.raises(ValueError, match="Unknown data objects"):
        validate_profile(profile, CONFIG)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_profiles.py -v
```

Expected: all 8 tests fail with `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Create `orgcompare/profiles.py`**

```python
"""Profile management — load, save, delete, and validate named selections."""
import yaml
from pathlib import Path


def load_profiles(profiles_path: str) -> dict:
    """Return {name: {metadata_types, data_objects}} from profiles.yaml.

    Creates an empty profiles.yaml if the file does not exist.
    """
    path = Path(profiles_path)
    if not path.exists():
        path.write_text("profiles: {}\n")
        return {}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("profiles", {})


def save_profile(
    profiles_path: str, name: str, metadata_types: list, data_objects: list
) -> None:
    """Create or overwrite a named profile."""
    profiles = load_profiles(profiles_path)
    profiles[name] = {"metadata_types": metadata_types, "data_objects": data_objects}
    _write(profiles_path, profiles)


def delete_profile(profiles_path: str, name: str) -> None:
    """Delete a named profile. No-op if the profile does not exist."""
    profiles = load_profiles(profiles_path)
    profiles.pop(name, None)
    _write(profiles_path, profiles)


def validate_profile(profile: dict, config: dict) -> None:
    """Raise ValueError if the profile references types/objects absent from config."""
    valid_metadata = set(config.get("metadata_types", []))
    valid_objects = {obj["name"] for obj in config.get("data_objects", [])}

    unknown_meta = set(profile.get("metadata_types", [])) - valid_metadata
    if unknown_meta:
        raise ValueError(f"Unknown metadata types in profile: {sorted(unknown_meta)}")

    unknown_objs = set(profile.get("data_objects", [])) - valid_objects
    if unknown_objs:
        raise ValueError(f"Unknown data objects in profile: {sorted(unknown_objs)}")


def _write(profiles_path: str, profiles: dict) -> None:
    with open(profiles_path, "w") as f:
        yaml.dump({"profiles": profiles}, f, default_flow_style=False, allow_unicode=True)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_profiles.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add orgcompare/profiles.py tests/test_profiles.py
git commit -m "feat: profiles module — load/save/delete/validate named selections"
```

---

## Task 2: `compare_metadata` optional type filter

**Files:**
- Modify: `orgcompare/compare.py` — add `metadata_types` parameter to `compare_metadata`
- Modify: `tests/test_compare.py` — add filter test

- [ ] **Step 1: Write the failing test**

Append to `tests/test_compare.py`:

```python
def test_metadata_filter_excludes_other_types():
    results = compare_metadata(
        str(FIXTURES_DIR / "DEVRCA"),
        str(FIXTURES_DIR / "UATR"),
        metadata_types=["Flow"],
    )
    types_found = {r.type for r in results}
    assert types_found <= {"Flow"}
    assert "ApexClass" not in types_found
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_compare.py::test_metadata_filter_excludes_other_types -v
```

Expected: FAIL — `compare_metadata() takes 2 positional arguments but 3 were given` (or similar).

- [ ] **Step 3: Add the optional parameter to `compare_metadata`**

In `orgcompare/compare.py`, change the function signature and add a filter at the top of the loop:

```python
def compare_metadata(
    source_dir: str, target_dir: str, metadata_types: list | None = None
) -> List[DiffResult]:
    """Compare metadata XML files between source and target directories.

    If metadata_types is provided, only files whose inferred type is in the
    list are included. Pass None (default) to include all types.
    """
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
            results.append(DiffResult(
                category="metadata", type=type_name, name=name,
                status="added", source_value=source_val, target_value={}, diff={},
            ))
        elif not in_source and in_target:
            target_val = _xml_to_dict(target_files[rel_path])
            results.append(DiffResult(
                category="metadata", type=type_name, name=name,
                status="removed", source_value={}, target_value=target_val, diff={},
            ))
        else:
            source_val = _xml_to_dict(source_files[rel_path])
            target_val = _xml_to_dict(target_files[rel_path])
            ddiff = DeepDiff(target_val, source_val, ignore_order=True)
            diff_dict = ddiff.to_dict() if ddiff else {}
            status = "modified" if diff_dict else "identical"
            results.append(DiffResult(
                category="metadata", type=type_name, name=name,
                status=status, source_value=source_val, target_value=target_val, diff=diff_dict,
            ))

    return results
```

- [ ] **Step 4: Run all compare tests to verify they pass**

```
pytest tests/test_compare.py -v
```

Expected: all tests PASS (existing tests still work because `metadata_types=None` is the default).

- [ ] **Step 5: Commit**

```bash
git add orgcompare/compare.py tests/test_compare.py
git commit -m "feat: compare_metadata accepts optional metadata_types filter"
```

---

## Task 3: `main.py` — argparse migration + selection flags

**Files:**
- Modify: `main.py` — replace `sys.argv` loop with `argparse`, add `--profile`/`--metadata`/`--objects`
- Create: `tests/test_main.py` — tests for `resolve_selection`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_main.py`:

```python
import argparse
import pytest
from main import resolve_selection

CONFIG = {
    "metadata_types": ["ApexClass", "Flow", "PermissionSet"],
    "data_objects": [
        {"name": "Product2", "query": "SELECT Id FROM Product2", "external_id": "Name"},
        {"name": "Pricebook2", "query": "SELECT Id FROM Pricebook2", "external_id": "Name"},
    ],
}


def _args(profile=None, metadata=None, objects=None):
    return argparse.Namespace(profile=profile, metadata=metadata, objects=objects)


def test_resolve_selection_defaults_to_full_config():
    meta, objs = resolve_selection(_args(), CONFIG)
    assert meta == CONFIG["metadata_types"]
    assert objs == CONFIG["data_objects"]


def test_resolve_selection_with_metadata_flag():
    meta, objs = resolve_selection(_args(metadata="ApexClass,Flow"), CONFIG)
    assert meta == ["ApexClass", "Flow"]
    assert objs == CONFIG["data_objects"]


def test_resolve_selection_with_objects_flag():
    meta, objs = resolve_selection(_args(objects="Product2"), CONFIG)
    assert meta == CONFIG["metadata_types"]
    assert [o["name"] for o in objs] == ["Product2"]


def test_resolve_selection_with_profile(tmp_path, monkeypatch):
    profiles_yaml = tmp_path / "profiles.yaml"
    profiles_yaml.write_text(
        "profiles:\n  quick:\n    metadata_types: [ApexClass]\n    data_objects: [Product2]\n"
    )
    monkeypatch.chdir(tmp_path)
    # copy config.yaml equivalent — resolve_selection reads profiles.yaml from cwd
    meta, objs = resolve_selection(_args(profile="quick"), CONFIG)
    assert meta == ["ApexClass"]
    assert [o["name"] for o in objs] == ["Product2"]


def test_resolve_selection_profile_not_found_exits(tmp_path, monkeypatch):
    profiles_yaml = tmp_path / "profiles.yaml"
    profiles_yaml.write_text("profiles: {}\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        resolve_selection(_args(profile="nonexistent"), CONFIG)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_main.py -v
```

Expected: all 5 fail — `resolve_selection` does not exist yet.

- [ ] **Step 3: Rewrite `main.py`**

Replace the entire contents of `main.py`:

```python
"""OrgCompare entry point — orchestrates retrieve, compare, report, serve, and deploy commands."""
import argparse
import sys
import yaml


def load_config() -> dict:
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def resolve_selection(args, config: dict) -> tuple:
    """Return (metadata_types, data_objects) based on CLI flags.

    Priority: --metadata/--objects > --profile > full config (default).
    """
    if args.metadata or args.objects:
        metadata_types = (
            [m.strip() for m in args.metadata.split(",")]
            if args.metadata
            else config["metadata_types"]
        )
        obj_names = (
            {o.strip() for o in args.objects.split(",")}
            if args.objects
            else {o["name"] for o in config["data_objects"]}
        )
        data_objects = [o for o in config["data_objects"] if o["name"] in obj_names]
        return metadata_types, data_objects

    if args.profile:
        from orgcompare.profiles import load_profiles, validate_profile

        profiles = load_profiles("profiles.yaml")
        if args.profile not in profiles:
            print(f"Profile '{args.profile}' not found in profiles.yaml")
            sys.exit(1)
        profile = profiles[args.profile]
        validate_profile(profile, config)
        obj_names = set(profile["data_objects"])
        data_objects = [o for o in config["data_objects"] if o["name"] in obj_names]
        return profile["metadata_types"], data_objects

    return config["metadata_types"], config["data_objects"]


def cmd_retrieve(config: dict, metadata_types: list, data_objects: list) -> None:
    from orgcompare.retrieve import retrieve_metadata, retrieve_data

    source = config["source_org"]
    target = config["target_org"]
    print(f"Retrieving metadata from {source}...")
    retrieve_metadata(source, metadata_types, f"output/retrieved/{source}")
    print(f"Retrieving metadata from {target}...")
    retrieve_metadata(target, metadata_types, f"output/retrieved/{target}")
    print(f"Retrieving data from {source}...")
    retrieve_data(source, data_objects, f"output/retrieved/{source}")
    print(f"Retrieving data from {target}...")
    retrieve_data(target, data_objects, f"output/retrieved/{target}")
    print("Done.")


def cmd_compare(config: dict, metadata_types: list, data_objects: list) -> None:
    from orgcompare.compare import compare_metadata, compare_data, save_results

    source = config["source_org"]
    target = config["target_org"]
    print("Comparing metadata...")
    meta_diffs = compare_metadata(
        f"output/retrieved/{source}",
        f"output/retrieved/{target}",
        metadata_types=metadata_types,
    )
    print("Comparing data...")
    data_diffs = compare_data(
        f"output/retrieved/{source}",
        f"output/retrieved/{target}",
        data_objects,
    )
    all_diffs = meta_diffs + data_diffs
    save_results(all_diffs, "output/reports/diff.json")
    total = len(all_diffs)
    different = sum(1 for r in all_diffs if r.status != "identical")
    print(f"Done. {different} differences out of {total} items. Results: output/reports/diff.json")


def cmd_report(config: dict, _metadata_types: list, _data_objects: list) -> None:
    from orgcompare.compare import load_results
    from orgcompare.report import generate_html, generate_csv

    results = load_results("output/reports/diff.json")
    generate_html(results, "output/reports/report.html", config["source_org"], config["target_org"])
    generate_csv(results, "output/reports")
    print("Report: output/reports/report.html")
    print("CSVs:   output/reports/<Type>_diff.csv")


def cmd_serve(_config: dict, _metadata_types: list, _data_objects: list) -> None:
    from orgcompare.server import run

    print("Starting web UI at http://localhost:5000")
    run()


def cmd_deploy(config: dict, _metadata_types: list, _data_objects: list) -> None:
    from orgcompare.compare import load_results
    from orgcompare.deploy import deploy_metadata, deploy_data

    results = load_results("output/reports/diff.json")
    target = config["target_org"]
    meta_items = [r for r in results if r.category == "metadata" and r.status != "identical"]
    data_items = [r for r in results if r.category == "data" and r.status != "identical"]
    if meta_items:
        result = deploy_metadata(meta_items, target)
        status = "OK" if result.get("success") else "FAILED"
        print(f"Metadata deploy: {status} — log: {result['log']}")
    if data_items:
        for r in deploy_data(data_items, config["data_objects"], target):
            status = "OK" if r.get("success") else "FAILED"
            print(f"Data deploy {r['object']}: {status} — log: {r.get('log', 'n/a')}")
    if not meta_items and not data_items:
        print("Nothing to deploy — no differences found.")


COMMANDS = {
    "retrieve": cmd_retrieve,
    "compare": cmd_compare,
    "report": cmd_report,
    "serve": cmd_serve,
    "deploy": cmd_deploy,
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="OrgCompare — compare Salesforce orgs",
        usage="python main.py [retrieve|compare|report|serve|deploy] ... [--profile NAME | --metadata TYPES --objects OBJS]",
    )
    parser.add_argument(
        "commands", nargs="+", choices=list(COMMANDS), help="Pipeline commands to run"
    )
    parser.add_argument("--profile", help="Named profile from profiles.yaml")
    parser.add_argument(
        "--metadata", help="Comma-separated metadata types, e.g. ApexClass,Flow"
    )
    parser.add_argument(
        "--objects", help="Comma-separated data object names, e.g. Product2,Pricebook2"
    )

    args = parser.parse_args()

    if args.profile and (args.metadata or args.objects):
        parser.error("--profile and --metadata/--objects are mutually exclusive")

    config = load_config()
    metadata_types, data_objects = resolve_selection(args, config)
    for cmd in args.commands:
        COMMANDS[cmd](config, metadata_types, data_objects)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_main.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Run the full test suite to check for regressions**

```
pytest -v
```

Expected: all existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: main.py argparse migration with --profile/--metadata/--objects flags"
```

---

## Task 4: `server.py` — profile endpoints + selection-aware run-compare

**Files:**
- Modify: `orgcompare/server.py`

- [ ] **Step 1: Replace `orgcompare/server.py` with the extended version**

```python
import yaml
from collections import defaultdict
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from orgcompare.compare import compare_data, compare_metadata, load_results, save_results
from orgcompare.deploy import deploy_data, deploy_metadata
from orgcompare.retrieve import retrieve_data, retrieve_metadata

_TEMPLATES_DIR = str(Path(__file__).parent.parent / "templates")
app = Flask(__name__, template_folder=_TEMPLATES_DIR)
DIFF_FILE = "output/reports/diff.json"
PROFILES_FILE = "profiles.yaml"


def _load_config() -> dict:
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def _build_summary(results: list) -> dict:
    summary = defaultdict(lambda: {"added": 0, "modified": 0, "removed": 0, "identical": 0})
    for r in results:
        summary[r.type][r.status] += 1
    return dict(summary)


@app.route("/")
def index():
    config = _load_config()
    results = load_results(DIFF_FILE) if Path(DIFF_FILE).exists() else []
    displayed = [r for r in results if r.status != "identical"]
    return render_template(
        "ui.html",
        source_org=config["source_org"],
        target_org=config["target_org"],
        results=[r.to_dict() for r in displayed],
        summary=_build_summary(results),
        all_metadata_types=config["metadata_types"],
        all_data_objects=[obj["name"] for obj in config["data_objects"]],
    )


@app.route("/api/run-compare", methods=["POST"])
def run_compare():
    config = _load_config()
    source = config["source_org"]
    target = config["target_org"]
    body = request.get_json(silent=True) or {}
    metadata_types = body.get("metadata_types") or config["metadata_types"]
    obj_names = set(body.get("data_objects") or [o["name"] for o in config["data_objects"]])
    data_objects = [o for o in config["data_objects"] if o["name"] in obj_names]
    try:
        retrieve_metadata(source, metadata_types, f"output/retrieved/{source}")
        retrieve_metadata(target, metadata_types, f"output/retrieved/{target}")
        retrieve_data(source, data_objects, f"output/retrieved/{source}")
        retrieve_data(target, data_objects, f"output/retrieved/{target}")
        meta_diffs = compare_metadata(
            f"output/retrieved/{source}",
            f"output/retrieved/{target}",
            metadata_types=metadata_types,
        )
        data_diffs = compare_data(
            f"output/retrieved/{source}",
            f"output/retrieved/{target}",
            data_objects,
        )
        all_diffs = meta_diffs + data_diffs
        save_results(all_diffs, DIFF_FILE)
        return jsonify({"status": "ok", "total": len(all_diffs)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/deploy", methods=["POST"])
def deploy():
    config = _load_config()
    target = config["target_org"]
    body = request.get_json()
    selected_names = set(body.get("names", []))
    selected_types = set(body.get("types", []))
    dry_run = body.get("dry_run", False)

    results = load_results(DIFF_FILE)
    selected = [
        r for r in results
        if r.name in selected_names and r.type in selected_types and r.status != "identical"
    ]

    meta_items = [r for r in selected if r.category == "metadata"]
    data_items = [r for r in selected if r.category == "data"]
    deploy_log = []

    if meta_items:
        deploy_log.append(deploy_metadata(meta_items, target, dry_run=dry_run))
    if data_items:
        deploy_log.extend(deploy_data(data_items, config["data_objects"], target, dry_run=dry_run))

    return jsonify({"status": "ok", "log": deploy_log})


@app.route("/profiles", methods=["GET"])
def get_profiles():
    from orgcompare.profiles import load_profiles

    return jsonify({"profiles": load_profiles(PROFILES_FILE)})


@app.route("/profiles", methods=["POST"])
def create_profile():
    from orgcompare.profiles import save_profile, validate_profile

    config = _load_config()
    body = request.get_json()
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    profile = {
        "metadata_types": body.get("metadata_types", []),
        "data_objects": body.get("data_objects", []),
    }
    try:
        validate_profile(profile, config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    save_profile(PROFILES_FILE, name, profile["metadata_types"], profile["data_objects"])
    return jsonify({"status": "ok"})


@app.route("/profiles/<name>", methods=["DELETE"])
def delete_profile_endpoint(name: str):
    from orgcompare.profiles import delete_profile

    delete_profile(PROFILES_FILE, name)
    return jsonify({"status": "ok"})


def run():
    app.run(debug=True, port=5000)
```

- [ ] **Step 2: Run the test suite to verify no regressions**

```
pytest -v
```

Expected: all existing tests PASS (server.py has no dedicated test file in the existing suite).

- [ ] **Step 3: Commit**

```bash
git add orgcompare/server.py
git commit -m "feat: server profile endpoints + selection-aware run-compare"
```

---

## Task 5: `templates/ui.html` — pre-run selection panel

**Files:**
- Modify: `templates/ui.html`

- [ ] **Step 1: Replace `templates/ui.html` with the selection-panel version**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>OrgCompare</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; color: #333; }
    h1 { color: #2c3e50; }
    .toolbar { margin-bottom: 16px; display: flex; gap: 10px; align-items: center; }
    button { padding: 8px 18px; cursor: pointer; border: none; border-radius: 4px; font-size: 14px; }
    .btn-primary { background: #2980b9; color: white; }
    .btn-success { background: #27ae60; color: white; }
    .btn-warning { background: #e67e22; color: white; }
    .btn-secondary { background: #95a5a6; color: white; }
    button:hover { opacity: 0.85; }
    table { border-collapse: collapse; width: 100%; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
    th { background: #2980b9; color: white; }
    tr:nth-child(even) { background: #f9f9f9; }
    .added { color: #27ae60; font-weight: bold; }
    .modified { color: #e67e22; font-weight: bold; }
    .removed { color: #e74c3c; font-weight: bold; }
    #status { padding: 10px; border-radius: 4px; background: #fff; border: 1px solid #ddd; display: none; margin-bottom: 10px; }
    .status-ok { border-color: #27ae60; color: #27ae60; }
    .status-error { border-color: #e74c3c; color: #e74c3c; }
    .diff-row { display: none; }
    .diff-row.open { display: table-row; }
    pre { font-size: 12px; background: #f8f8f8; padding: 8px; max-height: 220px; overflow-y: auto; margin: 0; }
    .summary-bar { display: flex; gap: 20px; margin-bottom: 16px; }
    .summary-card { background: white; padding: 10px 16px; border-radius: 4px; border: 1px solid #ddd; }
    .summary-card span { font-weight: bold; font-size: 18px; }
    .selection-panel { background: white; border: 1px solid #ddd; border-radius: 4px; padding: 14px 16px; margin-bottom: 16px; }
    .selection-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
    .selection-row:last-child { margin-bottom: 0; }
    .selection-row > label:first-child { min-width: 70px; font-weight: bold; color: #555; }
    .check-label { display: flex; align-items: center; gap: 4px; font-size: 14px; }
    select { padding: 5px 8px; border-radius: 4px; border: 1px solid #ccc; font-size: 14px; }
  </style>
</head>
<body>
  <h1>OrgCompare: {{ source_org }} → {{ target_org }}</h1>

  <div class="selection-panel">
    <div class="selection-row">
      <label>Profile:</label>
      <select id="profile-select" onchange="applyProfile()">
        <option value="">Custom</option>
      </select>
      <button class="btn-secondary" onclick="saveCurrentProfile()">Save current as...</button>
    </div>
    <div class="selection-row">
      <label>Metadata:</label>
      {% for type in all_metadata_types %}
      <label class="check-label">
        <input type="checkbox" class="meta-check" value="{{ type }}" checked onchange="onSelectionChange()"> {{ type }}
      </label>
      {% endfor %}
    </div>
    <div class="selection-row">
      <label>Data:</label>
      {% for obj in all_data_objects %}
      <label class="check-label">
        <input type="checkbox" class="obj-check" value="{{ obj }}" checked onchange="onSelectionChange()"> {{ obj }}
      </label>
      {% endfor %}
    </div>
  </div>

  <div class="toolbar">
    <button class="btn-primary" onclick="runCompare()">&#8635; Run Compare</button>
    <button class="btn-success" onclick="deploySelected()">&#8679; Deploy Selected</button>
    <button class="btn-warning" onclick="deployAll()">&#8679; Deploy All</button>
  </div>

  <div id="status"></div>

  <div class="summary-bar">
    {% for type_name, counts in summary.items() %}
    <div class="summary-card">
      <strong>{{ type_name }}</strong><br>
      <span class="added">+{{ counts.added }}</span>
      <span class="modified"> ~{{ counts.modified }}</span>
      <span class="removed"> -{{ counts.removed }}</span>
    </div>
    {% endfor %}
  </div>

  <table>
    <thead>
      <tr>
        <th><input type="checkbox" id="select-all" onchange="toggleAll(this)"></th>
        <th>Category</th>
        <th>Type</th>
        <th>Name</th>
        <th>Status</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      {% for r in results %}
      <tr>
        <td><input type="checkbox" class="row-check" data-name="{{ r.name }}" data-type="{{ r.type }}"></td>
        <td>{{ r.category }}</td>
        <td>{{ r.type }}</td>
        <td>{{ r.name }}</td>
        <td class="{{ r.status }}">{{ r.status }}</td>
        <td><a href="#" onclick="toggleDiff('diff-{{ loop.index }}'); return false;">view diff</a></td>
      </tr>
      <tr id="diff-{{ loop.index }}" class="diff-row">
        <td colspan="6"><pre>{{ r.diff | tojson(indent=2) if r.diff else ("Added in source" if r.status == "added" else "Removed from source") }}</pre></td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <script>
    // --- Profile state ---
    let profilesData = {};

    async function loadProfilesIntoDropdown() {
      const res = await fetch('/profiles');
      const data = await res.json();
      profilesData = data.profiles || {};
      const sel = document.getElementById('profile-select');
      // Remove all options except "Custom"
      while (sel.options.length > 1) sel.remove(1);
      for (const name of Object.keys(profilesData).sort()) {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        sel.appendChild(opt);
      }
    }

    function applyProfile() {
      const name = document.getElementById('profile-select').value;
      if (!name) return;
      const profile = profilesData[name];
      if (!profile) return;
      const metaSet = new Set(profile.metadata_types || []);
      const objSet = new Set(profile.data_objects || []);
      document.querySelectorAll('.meta-check').forEach(cb => {
        cb.checked = metaSet.has(cb.value);
      });
      document.querySelectorAll('.obj-check').forEach(cb => {
        cb.checked = objSet.has(cb.value);
      });
    }

    function onSelectionChange() {
      document.getElementById('profile-select').value = '';
    }

    async function saveCurrentProfile() {
      const name = prompt('Profile name:');
      if (!name || !name.trim()) return;
      const metadata_types = Array.from(document.querySelectorAll('.meta-check:checked')).map(c => c.value);
      const data_objects = Array.from(document.querySelectorAll('.obj-check:checked')).map(c => c.value);
      const res = await fetch('/profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), metadata_types, data_objects }),
      });
      const data = await res.json();
      if (data.status === 'ok') {
        await loadProfilesIntoDropdown();
        document.getElementById('profile-select').value = name.trim();
        showStatus(`Profile '${name.trim()}' saved.`);
      } else {
        showStatus(`Error: ${data.error}`, false);
      }
    }

    // --- Compare ---
    function getSelection() {
      return {
        metadata_types: Array.from(document.querySelectorAll('.meta-check:checked')).map(c => c.value),
        data_objects: Array.from(document.querySelectorAll('.obj-check:checked')).map(c => c.value),
      };
    }

    async function runCompare() {
      const selection = getSelection();
      showStatus('Running compare — this may take a minute...');
      const res = await fetch('/api/run-compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(selection),
      });
      const data = await res.json();
      if (data.status === 'ok') {
        showStatus(`Compare complete: ${data.total} items. Refreshing...`);
        setTimeout(() => location.reload(), 1500);
      } else {
        showStatus(`Error: ${data.message}`, false);
      }
    }

    // --- Deploy ---
    function toggleAll(cb) {
      document.querySelectorAll('.row-check').forEach(c => c.checked = cb.checked);
    }
    function toggleDiff(id) {
      document.getElementById(id).classList.toggle('open');
    }
    function showStatus(msg, ok = true) {
      const el = document.getElementById('status');
      el.style.display = 'block';
      el.className = ok ? 'status-ok' : 'status-error';
      el.textContent = msg;
    }
    function getSelected() {
      return Array.from(document.querySelectorAll('.row-check:checked')).map(c => ({
        name: c.dataset.name,
        type: c.dataset.type,
      }));
    }
    async function deploySelected() {
      const selected = getSelected();
      if (!selected.length) { showStatus('No items selected.', false); return; }
      showStatus(`Deploying ${selected.length} selected items...`);
      const res = await fetch('/api/deploy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          names: selected.map(s => s.name),
          types: [...new Set(selected.map(s => s.type))],
        }),
      });
      const data = await res.json();
      showStatus(data.status === 'ok' ? 'Deploy complete. Check output/deploy/ for logs.' : `Error: ${data.message}`, data.status === 'ok');
    }
    async function deployAll() {
      document.querySelectorAll('.row-check').forEach(c => c.checked = true);
      await deploySelected();
    }

    // --- Init ---
    loadProfilesIntoDropdown();
  </script>
</body>
</html>
```

- [ ] **Step 2: Run the full test suite to verify no regressions**

```
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add templates/ui.html
git commit -m "feat: pre-run selection panel with profile dropdown and checkboxes"
```

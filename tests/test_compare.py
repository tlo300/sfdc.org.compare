import json
from pathlib import Path
from tests.conftest import FIXTURES_DIR
from orgcompare.compare import compare_metadata, compare_data, save_results, load_results


def test_metadata_detects_modified():
    results = compare_metadata(
        str(FIXTURES_DIR / "DEVRCA"),
        str(FIXTURES_DIR / "UATR"),
    )
    modified = [r for r in results if r.name == "OrderService" and r.status == "modified"]
    assert len(modified) == 1
    diff = modified[0].diff
    assert diff  # should have changes


def test_metadata_detects_added():
    results = compare_metadata(
        str(FIXTURES_DIR / "DEVRCA"),
        str(FIXTURES_DIR / "UATR"),
    )
    added = [r for r in results if r.name == "NewClass" and r.status == "added"]
    assert len(added) == 1
    assert added[0].category == "metadata"
    assert added[0].type == "ApexClass"
    assert added[0].target_value == {}


def test_metadata_type_inferred_from_path():
    results = compare_metadata(
        str(FIXTURES_DIR / "DEVRCA"),
        str(FIXTURES_DIR / "UATR"),
    )
    for r in results:
        assert r.type == "ApexClass"


def test_data_detects_modified():
    data_objects = [{"name": "Product2", "query": "", "external_id": "Name"}]
    results = compare_data(
        str(FIXTURES_DIR / "DEVRCA"),
        str(FIXTURES_DIR / "UATR"),
        data_objects,
    )
    modified = [r for r in results if r.name == "Enterprise License" and r.status == "modified"]
    assert len(modified) == 1
    assert modified[0].category == "data"
    assert modified[0].type == "Product2"
    assert modified[0].diff  # has field-level changes


def test_data_detects_added():
    data_objects = [{"name": "Product2", "query": "", "external_id": "Name"}]
    results = compare_data(
        str(FIXTURES_DIR / "DEVRCA"),
        str(FIXTURES_DIR / "UATR"),
        data_objects,
    )
    added = [r for r in results if r.name == "Basic License"]
    assert len(added) == 1
    assert added[0].status == "added"
    assert added[0].target_value == {}


def test_data_detects_removed():
    data_objects = [{"name": "Product2", "query": "", "external_id": "Name"}]
    results = compare_data(
        str(FIXTURES_DIR / "DEVRCA"),
        str(FIXTURES_DIR / "UATR"),
        data_objects,
    )
    removed = [r for r in results if r.name == "Legacy License"]
    assert len(removed) == 1
    assert removed[0].status == "removed"
    assert removed[0].source_value == {}


def test_save_and_load_results(tmp_path):
    from orgcompare.models import DiffResult
    results = [
        DiffResult(
            category="data", type="Product2", name="Enterprise License",
            status="modified", source_value={"Name": "Enterprise License"},
            target_value={"Name": "Enterprise License"}, diff={"x": 1},
        )
    ]
    out_file = str(tmp_path / "diff.json")
    save_results(results, out_file)
    loaded = load_results(out_file)
    assert len(loaded) == 1
    assert loaded[0].name == "Enterprise License"
    assert loaded[0].diff == {"x": 1}


def test_metadata_filter_excludes_other_types():
    # Filter for only ApexClass — fixtures contain ApexClass files, so results should be non-empty
    results = compare_metadata(
        str(FIXTURES_DIR / "DEVRCA"),
        str(FIXTURES_DIR / "UATR"),
        metadata_types=["ApexClass"],
    )
    types_found = {r.type for r in results}
    assert types_found <= {"ApexClass"}
    assert len(results) > 0  # confirms the filter is not accidentally excluding everything

    # Filter for Flow — fixtures have no Flow files, result should be empty
    results_flow = compare_metadata(
        str(FIXTURES_DIR / "DEVRCA"),
        str(FIXTURES_DIR / "UATR"),
        metadata_types=["Flow"],
    )
    assert results_flow == []


def test_metadata_modified_has_xml_diff():
    results = compare_metadata(
        str(FIXTURES_DIR / "DEVRCA"),
        str(FIXTURES_DIR / "UATR"),
    )
    modified = [r for r in results if r.name == "OrderService" and r.status == "modified"]
    assert len(modified) == 1
    assert modified[0].xml_diff is not None
    assert modified[0].xml_diff.startswith("---")
    assert "+++" in modified[0].xml_diff
    # fromfile=target label (UATR), tofile=source label (DEVRCA)
    assert "UATR" in modified[0].xml_diff
    assert "DEVRCA" in modified[0].xml_diff


def test_metadata_added_has_xml_diff():
    results = compare_metadata(
        str(FIXTURES_DIR / "DEVRCA"),
        str(FIXTURES_DIR / "UATR"),
    )
    added = [r for r in results if r.name == "NewClass" and r.status == "added"]
    assert len(added) == 1
    assert added[0].xml_diff is not None
    # All lines are additions — fromfile=/dev/null
    assert "/dev/null" in added[0].xml_diff
    assert "DEVRCA" in added[0].xml_diff


def test_metadata_removed_has_xml_diff():
    results = compare_metadata(
        str(FIXTURES_DIR / "DEVRCA"),
        str(FIXTURES_DIR / "UATR"),
    )
    removed = [r for r in results if r.status == "removed"]
    assert len(removed) >= 1
    r = removed[0]
    assert r.xml_diff is not None
    # All lines are deletions — tofile=/dev/null
    assert "/dev/null" in r.xml_diff
    assert "UATR" in r.xml_diff


def test_metadata_identical_has_no_xml_diff():
    # identical items have xml_diff == None
    results = compare_metadata(
        str(FIXTURES_DIR / "DEVRCA"),
        str(FIXTURES_DIR / "UATR"),
    )
    identical = [r for r in results if r.status == "identical"]
    for r in identical:
        assert r.xml_diff is None

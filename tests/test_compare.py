from pathlib import Path
from tests.conftest import FIXTURES_DIR
from orgcompare.compare import compare_metadata


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

import json
import pytest
from orgcompare.discover import load_discovery_cache, save_discovery_cache
from unittest.mock import patch, MagicMock


def test_load_discovery_cache_returns_empty_when_no_file(tmp_path):
    result = load_discovery_cache(str(tmp_path / "discovered.json"))
    assert result == {}


def test_save_and_load_discovery_cache_roundtrip(tmp_path):
    path = str(tmp_path / "discovered.json")
    data = {"metadata_types": ["ApexClass", "Flow"], "data_objects": ["Account", "Product2"]}
    save_discovery_cache(path, data)
    assert load_discovery_cache(path) == data


def test_save_discovery_cache_overwrites_existing(tmp_path):
    path = str(tmp_path / "discovered.json")
    save_discovery_cache(path, {"metadata_types": ["ApexClass"], "data_objects": []})
    save_discovery_cache(path, {"metadata_types": ["Flow"], "data_objects": ["Contact"]})
    result = load_discovery_cache(path)
    assert result["metadata_types"] == ["Flow"]
    assert result["data_objects"] == ["Contact"]


def _mock_run(stdout: str, returncode: int = 0) -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


def test_list_all_metadata_types_parses_xmlName():
    payload = json.dumps({
        "status": 0,
        "result": {
            "metadataObjects": [
                {"xmlName": "ApexClass", "suffix": "cls"},
                {"xmlName": "Flow", "suffix": "flow"},
            ]
        }
    })
    with patch("orgcompare.discover.subprocess.run", return_value=_mock_run(payload)) as mock_run:
        from orgcompare.discover import _list_all_metadata_types
        result = _list_all_metadata_types("DEVRCA")
    assert result == ["ApexClass", "Flow"]
    mock_run.assert_called_once()


def test_type_has_content_returns_true_when_components_present():
    payload = json.dumps({
        "status": 0,
        "result": [{"type": "ApexClass", "fullName": "MyClass"}]
    })
    with patch("orgcompare.discover.subprocess.run", return_value=_mock_run(payload)):
        from orgcompare.discover import _type_has_content
        assert _type_has_content("DEVRCA", "ApexClass") is True


def test_type_has_content_returns_false_when_result_is_empty_list():
    payload = json.dumps({"status": 0, "result": []})
    with patch("orgcompare.discover.subprocess.run", return_value=_mock_run(payload)):
        from orgcompare.discover import _type_has_content
        assert _type_has_content("DEVRCA", "Flow") is False


def test_type_has_content_returns_false_when_result_is_null():
    payload = json.dumps({"status": 0, "result": None})
    with patch("orgcompare.discover.subprocess.run", return_value=_mock_run(payload)):
        from orgcompare.discover import _type_has_content
        assert _type_has_content("DEVRCA", "Report") is False


def test_type_has_content_returns_false_on_nonzero_returncode():
    with patch("orgcompare.discover.subprocess.run", return_value=_mock_run("", returncode=1)):
        from orgcompare.discover import _type_has_content
        assert _type_has_content("DEVRCA", "EmailTemplate") is False


def test_type_has_content_returns_false_on_invalid_json():
    with patch("orgcompare.discover.subprocess.run", return_value=_mock_run("not-json")):
        from orgcompare.discover import _type_has_content
        assert _type_has_content("DEVRCA", "ApexClass") is False


def test_discover_metadata_types_returns_only_types_with_content():
    with patch("orgcompare.discover._list_all_metadata_types", return_value=["ApexClass", "Flow", "Report"]), \
         patch("orgcompare.discover._type_has_content", side_effect=lambda org, t, emit=None: t in {"ApexClass", "Report"}):
        from orgcompare.discover import discover_metadata_types
        result = discover_metadata_types("DEVRCA")
    assert result == ["ApexClass", "Report"]  # sorted, Flow excluded


def test_discover_metadata_types_returns_sorted():
    with patch("orgcompare.discover._list_all_metadata_types", return_value=["Flow", "ApexClass"]), \
         patch("orgcompare.discover._type_has_content", side_effect=lambda org, t, emit=None: True):
        from orgcompare.discover import discover_metadata_types
        result = discover_metadata_types("DEVRCA")
    assert result == ["ApexClass", "Flow"]


def test_discover_data_objects_returns_sorted_names():
    payload = json.dumps({
        "status": 0,
        "result": {
            "records": [
                {"QualifiedApiName": "Contact"},
                {"QualifiedApiName": "Account"},
                {"QualifiedApiName": "MyObj__c"},
            ]
        }
    })
    with patch("orgcompare.discover.subprocess.run", return_value=_mock_run(payload)):
        from orgcompare.discover import discover_data_objects
        result = discover_data_objects("DEVRCA")
    assert result == ["Account", "Contact", "MyObj__c"]


def test_discover_data_objects_uses_entity_definition_query():
    payload = json.dumps({"status": 0, "result": {"records": []}})
    with patch("orgcompare.discover.subprocess.run", return_value=_mock_run(payload)) as mock_run:
        from orgcompare.discover import discover_data_objects
        discover_data_objects("DEVRCA")
    call_args = mock_run.call_args[0][0]
    assert "EntityDefinition" in " ".join(call_args)
    assert "LIMIT" in " ".join(call_args)
    assert "--target-org" in call_args
    assert "DEVRCA" in call_args
    assert "--use-tooling-api" in call_args


def test_run_discovery_returns_combined_result(tmp_path):
    cache_path = str(tmp_path / "discovered.json")
    with patch("orgcompare.discover.discover_metadata_types", return_value=["ApexClass", "Flow"]), \
         patch("orgcompare.discover.discover_data_objects", return_value=["Account", "Contact"]):
        from orgcompare.discover import run_discovery
        result = run_discovery("DEVRCA", cache_path)
    assert result == {"metadata_types": ["ApexClass", "Flow"], "data_objects": ["Account", "Contact"]}


def test_run_discovery_saves_to_cache(tmp_path):
    cache_path = str(tmp_path / "discovered.json")
    with patch("orgcompare.discover.discover_metadata_types", return_value=["Flow"]), \
         patch("orgcompare.discover.discover_data_objects", return_value=["Product2"]):
        from orgcompare.discover import run_discovery
        run_discovery("DEVRCA", cache_path)
    cached = json.loads((tmp_path / "discovered.json").read_text())
    assert cached == {"metadata_types": ["Flow"], "data_objects": ["Product2"]}


def test_run_discovery_calls_emit_quiet_on_start(tmp_path):
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

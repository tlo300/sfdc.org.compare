from unittest.mock import patch, MagicMock
from pathlib import Path
import json
import pytest

from orgcompare.retrieve import retrieve_metadata, retrieve_data


def test_retrieve_metadata_calls_sf_cli(tmp_path):
    with patch("orgcompare.retrieve.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        retrieve_metadata("DEVRCA", ["ApexClass", "Flow"], str(tmp_path))
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        any_sf = any(a.startswith("sf") for a in args)
        assert any_sf  # handles both "sf" and "sf.cmd"
        assert "project" in args
        assert "retrieve" in args
        assert "start" in args
        assert "--target-org" in args
        assert "DEVRCA" in args
        assert "--metadata" in args
        assert "ApexClass" in args
        assert "Flow" in args
        assert "--output-dir" in args


def test_retrieve_data_writes_json(tmp_path):
    fake_result = json.dumps({
        "result": {
            "records": [
                {"Id": "001", "Name": "Enterprise License", "IsActive": True}
            ]
        }
    })
    with patch("orgcompare.retrieve.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_result, stderr="")
        data_objects = [
            {"name": "Product2", "query": "SELECT Id, Name FROM Product2", "external_id": "Name"}
        ]
        retrieve_data("DEVRCA", data_objects, str(tmp_path))
        out_file = tmp_path / "data" / "Product2.json"
        assert out_file.exists()
        records = json.loads(out_file.read_text())
        assert len(records) == 1
        assert records[0]["Name"] == "Enterprise License"


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

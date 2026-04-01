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
        assert "sf" in args
        assert "project" in args
        assert "retrieve" in args
        assert "start" in args
        assert "--target-org" in args
        assert "DEVRCA" in args
        assert "ApexClass,Flow" in args
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

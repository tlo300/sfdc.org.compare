from unittest.mock import patch, MagicMock
from pathlib import Path

from orgcompare.models import DiffResult
from orgcompare.deploy import _build_package_xml, deploy_metadata


METADATA_DIFFS = [
    DiffResult(
        category="metadata", type="ApexClass", name="OrderService",
        status="modified", source_value={}, target_value={}, diff={},
    ),
    DiffResult(
        category="metadata", type="Flow", name="OrderFlow",
        status="added", source_value={}, target_value={}, diff={},
    ),
]


def test_build_package_xml_contains_types():
    xml = _build_package_xml(METADATA_DIFFS)
    assert "ApexClass" in xml
    assert "Flow" in xml
    assert "OrderService" in xml
    assert "OrderFlow" in xml
    assert "59.0" in xml


def test_build_package_xml_is_valid_xml():
    import xml.etree.ElementTree as ET
    xml = _build_package_xml(METADATA_DIFFS)
    ET.fromstring(xml)  # raises if invalid


def test_deploy_metadata_dry_run(tmp_path):
    with patch("orgcompare.deploy.Path") as mock_path_class:
        # Use real tmp_path for file ops
        pass
    result = deploy_metadata(METADATA_DIFFS, "UATR", dry_run=True)
    assert result["dry_run"] is True
    assert result["type"] == "metadata"
    assert Path(result["package"]).exists()


def test_deploy_metadata_calls_sf_cli(tmp_path):
    with patch("orgcompare.deploy.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Deploy OK", stderr="")
        result = deploy_metadata(METADATA_DIFFS, "UATR", dry_run=False)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "sf" in args
        assert "project" in args
        assert "deploy" in args
        assert "--target-org" in args
        assert "UATR" in args
        assert result["success"] is True

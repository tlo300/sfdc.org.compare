import json
import pytest
from orgcompare.discover import load_discovery_cache, save_discovery_cache


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

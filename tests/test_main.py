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

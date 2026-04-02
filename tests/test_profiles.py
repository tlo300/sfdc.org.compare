import pytest
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


def test_validate_profile_accepts_discovered_string_objects():
    """Discovered data_objects are plain strings; validate_profile must handle both formats."""
    config_with_discovered = {
        "metadata_types": ["ApexClass"],
        "data_objects": [
            {"name": "Product2", "query": "SELECT Id FROM Product2", "external_id": "Name"},
            "Opportunity",
        ],
    }
    profile = {"metadata_types": ["ApexClass"], "data_objects": ["Opportunity"]}
    validate_profile(profile, config_with_discovered)  # should not raise

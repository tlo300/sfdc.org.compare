"""Profile management — load, save, delete, and validate named selections."""
import yaml
from pathlib import Path


def load_profiles(profiles_path: str) -> dict:
    """Return {name: {metadata_types, data_objects}} from profiles.yaml.

    Creates an empty profiles.yaml if the file does not exist.
    """
    path = Path(profiles_path)
    if not path.exists():
        path.write_text("profiles: {}\n", encoding="utf-8")
        return {}
    with open(path, encoding="utf-8") as f:
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
    if name not in profiles:
        return
    profiles.pop(name)
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
    with open(profiles_path, "w", encoding="utf-8") as f:
        yaml.dump({"profiles": profiles}, f, default_flow_style=False, allow_unicode=True)

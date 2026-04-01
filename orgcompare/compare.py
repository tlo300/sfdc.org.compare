"""
Metadata comparison module: compares Salesforce metadata XML files between two org directories.
"""
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

from deepdiff import DeepDiff

from orgcompare.models import DiffResult


DIR_TO_TYPE = {
    "classes": "ApexClass",
    "triggers": "ApexTrigger",
    "objects": "CustomObject",
    "flows": "Flow",
    "permissionsets": "PermissionSet",
    "lwc": "LightningComponentBundle",
    "validationRules": "ValidationRule",
}


def _xml_to_dict(file_path: Path) -> dict:
    tree = ET.parse(file_path)
    root = tree.getroot()
    return _element_to_dict(root)


def _element_to_dict(element) -> dict:
    result = {}
    for child in element:
        tag = child.tag.split("}")[-1]
        if len(child) == 0:
            result[tag] = child.text
        else:
            child_dict = _element_to_dict(child)
            if tag in result:
                if not isinstance(result[tag], list):
                    result[tag] = [result[tag]]
                result[tag].append(child_dict)
            else:
                result[tag] = child_dict
    return result


def _infer_type(rel_path: Path) -> str:
    parts = rel_path.parts
    if parts:
        return DIR_TO_TYPE.get(parts[0], parts[0])
    return "Unknown"


def _clean_name(rel_path: Path) -> str:
    name = rel_path.name
    for suffix in ["-meta.xml", ".cls", ".trigger", ".flow", ".permissionset", ".object"]:
        name = name.replace(suffix, "")
    return name


def compare_metadata(
    source_dir: str, target_dir: str, metadata_types: list | None = None
) -> List[DiffResult]:
    """Compare metadata XML files between source and target directories.

    If metadata_types is provided, only files whose inferred type is in the
    list are included. Pass None (default) to include all types.
    """
    source_path = Path(source_dir)
    target_path = Path(target_dir)

    source_files = {
        f.relative_to(source_path): f
        for f in source_path.rglob("*-meta.xml")
    }
    target_files = {
        f.relative_to(target_path): f
        for f in target_path.rglob("*-meta.xml")
    }

    results = []
    for rel_path in sorted(set(source_files) | set(target_files)):
        type_name = _infer_type(rel_path)
        if metadata_types is not None and type_name not in metadata_types:
            continue
        name = _clean_name(rel_path)
        in_source = rel_path in source_files
        in_target = rel_path in target_files

        if in_source and not in_target:
            source_val = _xml_to_dict(source_files[rel_path])
            results.append(DiffResult(
                category="metadata", type=type_name, name=name,
                status="added", source_value=source_val, target_value={}, diff={},
            ))
        elif not in_source and in_target:
            target_val = _xml_to_dict(target_files[rel_path])
            results.append(DiffResult(
                category="metadata", type=type_name, name=name,
                status="removed", source_value={}, target_value=target_val, diff={},
            ))
        else:
            source_val = _xml_to_dict(source_files[rel_path])
            target_val = _xml_to_dict(target_files[rel_path])
            ddiff = DeepDiff(target_val, source_val, ignore_order=True)
            diff_dict = json.loads(ddiff.to_json()) if ddiff else {}
            status = "modified" if diff_dict else "identical"
            results.append(DiffResult(
                category="metadata", type=type_name, name=name,
                status=status, source_value=source_val, target_value=target_val, diff=diff_dict,
            ))

    return results


def compare_data(source_dir: str, target_dir: str, data_objects: list) -> List[DiffResult]:
    """Compare data records between source and target. Matches by external_id field."""
    results = []

    for obj_config in data_objects:
        obj_name = obj_config["name"]
        external_id = obj_config.get("external_id", "Name")

        source_file = Path(source_dir) / "data" / f"{obj_name}.json"
        target_file = Path(target_dir) / "data" / f"{obj_name}.json"

        source_records = json.loads(source_file.read_text()) if source_file.exists() else []
        target_records = json.loads(target_file.read_text()) if target_file.exists() else []

        def to_indexed(records: list) -> dict:
            return {
                str(r[external_id]): {k: v for k, v in r.items() if k != "attributes"}
                for r in records
                if external_id in r
            }

        source_indexed = to_indexed(source_records)
        target_indexed = to_indexed(target_records)
        source_keys = set(source_indexed)
        target_keys = set(target_indexed)

        for key in sorted(source_keys - target_keys):
            results.append(DiffResult(
                category="data", type=obj_name, name=key,
                status="added", source_value=source_indexed[key], target_value={}, diff={},
            ))

        for key in sorted(target_keys - source_keys):
            results.append(DiffResult(
                category="data", type=obj_name, name=key,
                status="removed", source_value={}, target_value=target_indexed[key], diff={},
            ))

        for key in sorted(source_keys & target_keys):
            src = {k: v for k, v in source_indexed[key].items() if k != "Id"}
            tgt = {k: v for k, v in target_indexed[key].items() if k != "Id"}
            ddiff = DeepDiff(tgt, src, ignore_order=True)
            diff_dict = json.loads(ddiff.to_json()) if ddiff else {}
            status = "modified" if diff_dict else "identical"
            results.append(DiffResult(
                category="data", type=obj_name, name=key,
                status=status, source_value=source_indexed[key],
                target_value=target_indexed[key], diff=diff_dict,
            ))

    return results


def save_results(results: List[DiffResult], output_file: str) -> None:
    """Serialize DiffResult list to JSON file."""
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump([r.to_dict() for r in results], f, indent=2)


def load_results(input_file: str) -> List[DiffResult]:
    """Deserialize DiffResult list from JSON file."""
    with open(input_file) as f:
        return [DiffResult.from_dict(d) for d in json.load(f)]

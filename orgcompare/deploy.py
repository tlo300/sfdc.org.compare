import subprocess
from datetime import datetime
from pathlib import Path
from typing import List
from xml.dom.minidom import parseString
from xml.etree.ElementTree import Element, SubElement, tostring

from orgcompare.models import DiffResult

DEPLOY_DIR = Path("output/deploy")

METADATA_TYPE_TO_XML_NAME = {
    "ApexClass": "ApexClass",
    "ApexTrigger": "ApexTrigger",
    "Flow": "Flow",
    "PermissionSet": "PermissionSet",
    "LightningComponentBundle": "LightningComponentBundle",
    "ValidationRule": "ValidationRule",
    "CustomObject": "CustomObject",
}


def _build_package_xml(diff_results: List[DiffResult], api_version: str = "59.0") -> str:
    """Build a Salesforce package.xml manifest from a list of DiffResults."""
    package = Element("Package", xmlns="http://soap.sforce.com/2006/04/metadata")
    version_el = SubElement(package, "version")
    version_el.text = api_version

    by_type: dict = {}
    for r in diff_results:
        xml_name = METADATA_TYPE_TO_XML_NAME.get(r.type, r.type)
        by_type.setdefault(xml_name, []).append(r.name)

    for type_name in sorted(by_type):
        types_el = SubElement(package, "types")
        name_el = SubElement(types_el, "name")
        name_el.text = type_name
        for member in sorted(by_type[type_name]):
            member_el = SubElement(types_el, "members")
            member_el.text = member

    raw = tostring(package, encoding="unicode")
    dom = parseString(f'<?xml version="1.0" encoding="UTF-8"?>{raw}')
    lines = dom.toprettyxml(indent="    ").splitlines()
    return "\n".join(lines[1:])  # strip the extra <?xml?> declaration


def deploy_metadata(
    diff_results: List[DiffResult],
    target_org: str,
    dry_run: bool = False,
) -> dict:
    """Build package.xml and deploy metadata from source to target_org."""
    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    package_path = DEPLOY_DIR / f"package_{timestamp}.xml"
    package_xml = _build_package_xml(diff_results)
    package_path.write_text(package_xml, encoding="utf-8")

    log_path = DEPLOY_DIR / f"deploy_{timestamp}.log"

    if dry_run:
        log_path.write_text(f"[DRY RUN] Would deploy:\n{package_xml}")
        return {"type": "metadata", "dry_run": True, "package": str(package_path), "log": str(log_path)}

    result = subprocess.run(
        ["sf", "project", "deploy", "start", "--manifest", str(package_path), "--target-org", target_org],
        capture_output=True,
        text=True,
    )
    log_path.write_text(result.stdout + result.stderr)
    return {
        "type": "metadata",
        "dry_run": False,
        "package": str(package_path),
        "log": str(log_path),
        "success": result.returncode == 0,
        "output": result.stdout,
    }


def deploy_data(
    diff_results: List[DiffResult],
    data_objects_config: List[dict],
    target_org: str,
    dry_run: bool = False,
) -> List[dict]:
    """Export modified/added records to CSV and upsert into target_org.

    Placeholder for Task 10 — raises NotImplementedError until then.
    """
    raise NotImplementedError("deploy_data not yet implemented — see Task 10")

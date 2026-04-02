import json
import subprocess
import sys
from pathlib import Path

# On Windows the sf CLI is a .cmd file; use sf.cmd so subprocess can find it
# without needing shell=True (which breaks argument passing on Windows).
_SF_CMD = "sf.cmd" if sys.platform == "win32" else "sf"


def retrieve_metadata(org_alias: str, metadata_types: list, output_dir: str, emit=None) -> None:
    """Retrieve metadata from org to output_dir using sf CLI.

    Files are placed directly in output_dir in SFDX source format:
      output_dir/classes/ClassName.cls-meta.xml
      output_dir/flows/FlowName.flow-meta.xml
    """
    if not metadata_types:
        return
    if emit:
        emit("normal", f"Retrieving metadata from {org_alias}... ({len(metadata_types)} types)")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    metadata_flags = []
    for t in metadata_types:
        metadata_flags += ["--metadata", t]
    cmd = (
        [_SF_CMD, "project", "retrieve", "start"]
        + metadata_flags
        + ["--target-org", org_alias, "--output-dir", str(output_path)]
    )
    if emit:
        emit("debug", f"  {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"sf project retrieve failed for {org_alias}:\n{result.stderr or result.stdout}"
        )
    if emit:
        emit("normal", f"  Metadata retrieved from {org_alias}")


def retrieve_data(org_alias: str, data_objects: list, output_dir: str, emit=None) -> None:
    """Query records from org and save each object as JSON.

    Saves to output_dir/data/<ObjectName>.json as a list of records.
    """
    if emit:
        emit("normal", f"Retrieving data from {org_alias}... ({len(data_objects)} objects)")
    data_path = Path(output_dir) / "data"
    data_path.mkdir(parents=True, exist_ok=True)
    for obj in data_objects:
        cmd = [
            _SF_CMD, "data", "query",
            "--query", obj["query"],
            "--target-org", org_alias,
            "--result-format", "json",
        ]
        if emit:
            emit("debug", f"  {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        data = json.loads(result.stdout)
        records = data.get("result", {}).get("records", [])
        out_file = data_path / f"{obj['name']}.json"
        out_file.write_text(json.dumps(records, indent=2))
        if emit:
            emit("normal", f"  {obj['name']}: {len(records)} records")

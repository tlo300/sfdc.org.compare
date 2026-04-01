import json
import subprocess
from pathlib import Path


def retrieve_metadata(org_alias: str, metadata_types: list, output_dir: str) -> None:
    """Retrieve metadata from org to output_dir using sf CLI.

    Files are placed directly in output_dir in SFDX source format:
      output_dir/classes/ClassName.cls-meta.xml
      output_dir/flows/FlowName.flow-meta.xml
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    types_arg = ",".join(metadata_types)
    subprocess.run(
        [
            "sf", "project", "retrieve", "start",
            "--metadata", types_arg,
            "--target-org", org_alias,
            "--output-dir", str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def retrieve_data(org_alias: str, data_objects: list, output_dir: str) -> None:
    """Query records from org and save each object as JSON.

    Saves to output_dir/data/<ObjectName>.json as a list of records.
    """
    data_path = Path(output_dir) / "data"
    data_path.mkdir(parents=True, exist_ok=True)
    for obj in data_objects:
        result = subprocess.run(
            [
                "sf", "data", "query",
                "--query", obj["query"],
                "--target-org", org_alias,
                "--result-format", "json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
        records = data.get("result", {}).get("records", [])
        out_file = data_path / f"{obj['name']}.json"
        out_file.write_text(json.dumps(records, indent=2))

"""Report generation module: produces HTML and CSV outputs from DiffResult lists."""
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader

from orgcompare.models import DiffResult

# Locate the templates directory relative to this file so it works regardless
# of the working directory from which the code is invoked.
_TEMPLATES_DIR = str(Path(__file__).parent.parent / "templates")


def _build_summary(results: List[DiffResult]) -> dict:
    summary = defaultdict(lambda: {"added": 0, "modified": 0, "removed": 0, "identical": 0})
    for r in results:
        summary[r.type][r.status] += 1
    return dict(summary)


def _group_by_type(results: List[DiffResult]) -> dict:
    grouped = defaultdict(list)
    for r in results:
        grouped[r.type].append(r)
    return dict(grouped)


def generate_html(
    results: List[DiffResult],
    output_file: str,
    source_org: str,
    target_org: str,
    show_identical: bool = False,
    templates_dir: str = None,
) -> None:
    """Render self-contained HTML report from DiffResult list."""
    if templates_dir is None:
        templates_dir = _TEMPLATES_DIR
    env = Environment(loader=FileSystemLoader(templates_dir))
    env.filters["tojson"] = json.dumps
    template = env.get_template("report.html")
    displayed = results if show_identical else [r for r in results if r.status != "identical"]
    html = template.render(
        source_org=source_org,
        target_org=target_org,
        summary=_build_summary(results),
        grouped_diffs=_group_by_type(displayed),
    )
    out = Path(output_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")


def generate_csv(results: List[DiffResult], output_dir: str) -> None:
    """Write one CSV per object type with field-level diff rows."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    for type_name, diffs in _group_by_type(results).items():
        rows = []
        for diff in diffs:
            if diff.status == "identical":
                continue
            if diff.diff:
                for change_type, changes in diff.diff.items():
                    if isinstance(changes, dict):
                        for field, change in changes.items():
                            if isinstance(change, dict):
                                rows.append({
                                    "name": diff.name,
                                    "status": diff.status,
                                    "field": field,
                                    "source_value": str(change.get("new_value", "")),
                                    "target_value": str(change.get("old_value", "")),
                                })
                            else:
                                rows.append({
                                    "name": diff.name, "status": diff.status,
                                    "field": field, "source_value": str(change), "target_value": "",
                                })
                    else:
                        rows.append({
                            "name": diff.name, "status": diff.status,
                            "field": change_type, "source_value": str(changes), "target_value": "",
                        })
            else:
                rows.append({
                    "name": diff.name, "status": diff.status,
                    "field": "", "source_value": "", "target_value": "",
                })
        if rows:
            csv_file = output_path / f"{type_name}_diff.csv"
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["name", "status", "field", "source_value", "target_value"]
                )
                writer.writeheader()
                writer.writerows(rows)

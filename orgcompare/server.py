import yaml
from collections import defaultdict
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from orgcompare.compare import compare_data, compare_metadata, load_results, save_results
from orgcompare.deploy import deploy_data, deploy_metadata
from orgcompare.retrieve import retrieve_data, retrieve_metadata

_TEMPLATES_DIR = str(Path(__file__).parent.parent / "templates")
app = Flask(__name__, template_folder=_TEMPLATES_DIR)
DIFF_FILE = "output/reports/diff.json"


def _load_config() -> dict:
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def _build_summary(results: list) -> dict:
    summary = defaultdict(lambda: {"added": 0, "modified": 0, "removed": 0, "identical": 0})
    for r in results:
        summary[r.type][r.status] += 1
    return dict(summary)


@app.route("/")
def index():
    config = _load_config()
    results = load_results(DIFF_FILE) if Path(DIFF_FILE).exists() else []
    displayed = [r for r in results if r.status != "identical"]
    return render_template(
        "ui.html",
        source_org=config["source_org"],
        target_org=config["target_org"],
        results=[r.to_dict() for r in displayed],
        summary=_build_summary(results),
    )


@app.route("/api/run-compare", methods=["POST"])
def run_compare():
    config = _load_config()
    source = config["source_org"]
    target = config["target_org"]
    try:
        retrieve_metadata(source, config["metadata_types"], f"output/retrieved/{source}")
        retrieve_metadata(target, config["metadata_types"], f"output/retrieved/{target}")
        retrieve_data(source, config["data_objects"], f"output/retrieved/{source}")
        retrieve_data(target, config["data_objects"], f"output/retrieved/{target}")
        meta_diffs = compare_metadata(
            f"output/retrieved/{source}", f"output/retrieved/{target}"
        )
        data_diffs = compare_data(
            f"output/retrieved/{source}", f"output/retrieved/{target}",
            config["data_objects"],
        )
        all_diffs = meta_diffs + data_diffs
        save_results(all_diffs, DIFF_FILE)
        return jsonify({"status": "ok", "total": len(all_diffs)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/deploy", methods=["POST"])
def deploy():
    config = _load_config()
    target = config["target_org"]
    body = request.get_json()
    selected_names = set(body.get("names", []))
    selected_types = set(body.get("types", []))
    dry_run = body.get("dry_run", False)

    results = load_results(DIFF_FILE)
    selected = [
        r for r in results
        if r.name in selected_names and r.type in selected_types and r.status != "identical"
    ]

    meta_items = [r for r in selected if r.category == "metadata"]
    data_items = [r for r in selected if r.category == "data"]
    deploy_log = []

    if meta_items:
        deploy_log.append(deploy_metadata(meta_items, target, dry_run=dry_run))
    if data_items:
        deploy_log.extend(deploy_data(data_items, config["data_objects"], target, dry_run=dry_run))

    return jsonify({"status": "ok", "log": deploy_log})


def run():
    app.run(debug=True, port=5000)

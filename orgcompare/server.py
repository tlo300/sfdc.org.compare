import yaml
from collections import defaultdict
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from orgcompare.compare import compare_data, compare_metadata, load_results, save_results
from orgcompare.deploy import deploy_data, deploy_metadata
from orgcompare.discover import load_discovery_cache, run_discovery
from orgcompare.profiles import delete_profile, load_profiles, save_profile, validate_profile
from orgcompare.retrieve import retrieve_data, retrieve_metadata

_TEMPLATES_DIR = str(Path(__file__).parent.parent / "templates")
app = Flask(__name__, template_folder=_TEMPLATES_DIR)
app.config["TEMPLATES_AUTO_RELOAD"] = True
DIFF_FILE = "output/reports/diff.json"
PROFILES_FILE = "profiles.yaml"
DISCOVERY_FILE = "discovered.json"


@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


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
    discovered = load_discovery_cache(DISCOVERY_FILE)
    return render_template(
        "ui.html",
        source_org=config["source_org"],
        target_org=config["target_org"],
        discovered_metadata=discovered.get("metadata_types", []),
        discovered_objects=discovered.get("data_objects", []),
    )


@app.route("/api/run-compare", methods=["POST"])
def run_compare():
    config = _load_config()
    source = config["source_org"]
    target = config["target_org"]
    body = request.get_json(silent=True) or {}
    client_metadata = body.get("metadata_types")
    metadata_types = client_metadata if client_metadata is not None else config["metadata_types"]
    client_objects = body.get("data_objects")
    if client_objects is not None:
        known = {o["name"]: o for o in config["data_objects"]}
        data_objects = [
            known[name] if name in known
            else {"name": name, "query": f"SELECT FIELDS(ALL) FROM {name} LIMIT 200", "external_id": "Id"}
            for name in client_objects
        ]
    else:
        data_objects = config["data_objects"]
    try:
        retrieve_metadata(source, metadata_types, f"output/retrieved/{source}")
        retrieve_metadata(target, metadata_types, f"output/retrieved/{target}")
        retrieve_data(source, data_objects, f"output/retrieved/{source}")
        retrieve_data(target, data_objects, f"output/retrieved/{target}")
        meta_diffs = compare_metadata(
            f"output/retrieved/{source}",
            f"output/retrieved/{target}",
            metadata_types=metadata_types,
        )
        data_diffs = compare_data(
            f"output/retrieved/{source}",
            f"output/retrieved/{target}",
            data_objects,
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


@app.route("/profiles", methods=["GET"])
def get_profiles():
    return jsonify({"profiles": load_profiles(PROFILES_FILE)})


@app.route("/profiles", methods=["POST"])
def create_profile():
    config = _load_config()
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    profile = {
        "metadata_types": body.get("metadata_types", []),
        "data_objects": body.get("data_objects", []),
    }
    try:
        validate_profile(profile, config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    save_profile(PROFILES_FILE, name, profile["metadata_types"], profile["data_objects"])
    return jsonify({"status": "ok"})


@app.route("/profiles/<name>", methods=["DELETE"])
def delete_profile_endpoint(name: str):
    delete_profile(PROFILES_FILE, name)
    return jsonify({"status": "ok"})


@app.route("/api/results", methods=["GET"])
def get_results():
    results = load_results(DIFF_FILE) if Path(DIFF_FILE).exists() else []
    displayed = [r for r in results if r.status != "identical"]
    return jsonify({
        "results": [r.to_dict() for r in displayed],
        "summary": _build_summary(results),
    })


@app.route("/api/discover", methods=["GET"])
def get_discover():
    cached = load_discovery_cache(DISCOVERY_FILE)
    if not cached:
        return jsonify({"cached": False})
    return jsonify(cached)


@app.route("/api/discover", methods=["POST"])
def post_discover():
    config = _load_config()
    try:
        result = run_discovery(config["source_org"], DISCOVERY_FILE)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def run():
    app.run(debug=True, port=5000)

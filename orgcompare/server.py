import json
import queue
import subprocess
import sys
import threading
import uuid
import yaml
from collections import defaultdict
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request
from flask import stream_with_context

from orgcompare.compare import compare_data, compare_metadata, load_results, save_results
from orgcompare.deploy import deploy_data, deploy_metadata
from orgcompare.discover import load_discovery_cache, run_discovery
from orgcompare.orgs import add_org, bootstrap_orgs, load_orgs, remove_org, set_selection
from orgcompare.profiles import delete_profile, load_profiles, save_profile, validate_profile
from orgcompare.retrieve import retrieve_data, retrieve_metadata

_TEMPLATES_DIR = str(Path(__file__).parent.parent / "templates")
app = Flask(__name__, template_folder=_TEMPLATES_DIR)
app.config["TEMPLATES_AUTO_RELOAD"] = True
DIFF_FILE = "output/reports/diff.json"
PROFILES_FILE = "profiles.yaml"
DISCOVERY_FILE = "discovered.json"
ORGS_FILE = "orgs.yaml"
_LOGIN_JOBS: dict = {}  # job_id -> {"status": str} or {"status": str, "error": str}


@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


def _load_config() -> dict:
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def _load_orgs() -> dict:
    """Bootstrap orgs.yaml from config.yaml if absent, then return orgs data."""
    bootstrap_orgs(ORGS_FILE, "config.yaml")
    return load_orgs(ORGS_FILE)


def _build_summary(results: list) -> dict:
    summary = defaultdict(lambda: {"added": 0, "modified": 0, "removed": 0, "identical": 0})
    for r in results:
        summary[r.type][r.status] += 1
    return dict(summary)


def _run_login(job_id: str, alias: str, name: str, instance_url: str) -> None:
    """Run `sf org login web` in a background thread and update _LOGIN_JOBS."""
    try:
        sf = "sf.cmd" if sys.platform == "win32" else "sf"
        result = subprocess.run(
            [sf, "org", "login", "web", "--alias", alias, "--instance-url", instance_url],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            try:
                add_org(ORGS_FILE, alias, name)
                _LOGIN_JOBS[job_id] = {"status": "done"}
            except ValueError as e:
                _LOGIN_JOBS[job_id] = {"status": "error", "error": str(e)}
        else:
            _LOGIN_JOBS[job_id] = {
                "status": "error",
                "error": result.stderr.strip() or "Login failed",
            }
    except Exception as e:
        _LOGIN_JOBS[job_id] = {"status": "error", "error": str(e)}


@app.route("/")
def index():
    orgs_data = _load_orgs()
    discovered = load_discovery_cache(DISCOVERY_FILE)
    return render_template(
        "ui.html",
        source_org=orgs_data["selection"]["source"],
        target_org=orgs_data["selection"]["target"],
        discovered_metadata=discovered.get("metadata_types", []),
        discovered_objects=discovered.get("data_objects", []),
    )


@app.route("/api/run-compare", methods=["POST"])
def run_compare():
    config = _load_config()
    orgs_data = _load_orgs()
    source = orgs_data["selection"]["source"]
    target = orgs_data["selection"]["target"]
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
    target = _load_orgs()["selection"]["target"]
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
    discovered = load_discovery_cache(DISCOVERY_FILE)
    if discovered.get("data_objects"):
        config = dict(config, data_objects=list(config.get("data_objects", [])) + discovered["data_objects"])
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


@app.route("/api/orgs", methods=["GET"])
def get_orgs():
    return jsonify(_load_orgs())


@app.route("/api/orgs", methods=["POST"])
def post_org():
    body = request.get_json(silent=True) or {}
    alias = (body.get("alias") or "").strip()
    name = (body.get("name") or "").strip()
    if not alias or not name:
        return jsonify({"error": "alias and name are required"}), 400
    try:
        add_org(ORGS_FILE, alias, name)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"status": "ok"})


@app.route("/api/orgs/selection", methods=["PATCH"])
def patch_org_selection():
    _load_orgs()  # ensure orgs.yaml is bootstrapped before set_selection reads it
    body = request.get_json(silent=True) or {}
    source = body.get("source", "")
    target = body.get("target", "")
    try:
        set_selection(ORGS_FILE, source, target)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"status": "ok"})


@app.route("/api/orgs/<alias>", methods=["DELETE"])
def delete_org(alias: str):
    remove_org(ORGS_FILE, alias)
    return jsonify({"status": "ok"})


@app.route("/api/orgs/login", methods=["POST"])
def start_login():
    body = request.get_json(silent=True) or {}
    alias = (body.get("alias") or "").strip()
    name = (body.get("name") or "").strip()
    instance_url = (body.get("instance_url") or "https://test.salesforce.com").strip()
    if not alias or not name:
        return jsonify({"error": "alias and name are required"}), 400
    if instance_url not in ("https://login.salesforce.com", "https://test.salesforce.com"):
        return jsonify({"error": "invalid instance_url"}), 400
    job_id = str(uuid.uuid4())
    _LOGIN_JOBS[job_id] = {"status": "running"}
    threading.Thread(
        target=_run_login, args=(job_id, alias, name, instance_url), daemon=True
    ).start()
    return jsonify({"job_id": job_id})


@app.route("/api/orgs/login/status/<job_id>")
def login_status(job_id: str):
    job = _LOGIN_JOBS.get(job_id)
    if not job:
        return jsonify({"error": "unknown job"}), 404
    return jsonify(job)


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
    try:
        result = run_discovery(_load_orgs()["selection"]["source"], DISCOVERY_FILE)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/discover/stream")
def discover_stream():
    orgs_data = _load_orgs()
    source = orgs_data["selection"]["source"]
    ignore_empty = request.args.get("ignoreEmpty") == "true"
    q = queue.Queue()

    def emit(level, msg, **extra):
        q.put({"level": level, "msg": msg, **extra})

    def worker():
        try:
            result = run_discovery(source, DISCOVERY_FILE, ignore_empty=ignore_empty, emit=emit)
            q.put({
                "level": "quiet",
                "msg": f"Done \u2014 {len(result['metadata_types'])} metadata types, {len(result['data_objects'])} objects",
                "done": True,
                **result,
            })
        except Exception as e:
            q.put({"level": "error", "msg": str(e), "done": True})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def generate():
        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.route("/api/compare/stream")
def compare_stream():
    config = _load_config()
    orgs_data = _load_orgs()
    source = orgs_data["selection"]["source"]
    target = orgs_data["selection"]["target"]

    raw_meta = request.args.get("metadata_types")
    raw_objs = request.args.get("data_objects")

    try:
        metadata_types = json.loads(raw_meta) if raw_meta is not None else config["metadata_types"]
        if raw_objs is not None:
            obj_names = json.loads(raw_objs)
            known = {o["name"]: o for o in config["data_objects"]}
            data_objects = [
                known[name] if name in known
                else {"name": name, "query": f"SELECT FIELDS(ALL) FROM {name} LIMIT 200", "external_id": "Id"}
                for name in obj_names
            ]
        else:
            data_objects = config["data_objects"]
    except json.JSONDecodeError as e:
        return jsonify({"status": "error", "message": f"Invalid query parameters: {e}"}), 400

    q = queue.Queue()

    def emit(level, msg, **extra):
        q.put({"level": level, "msg": msg, **extra})

    def worker():
        try:
            emit("quiet", f"Starting compare: {source} \u2192 {target}...")
            retrieve_metadata(source, metadata_types, f"output/retrieved/{source}", emit=emit)
            retrieve_metadata(target, metadata_types, f"output/retrieved/{target}", emit=emit)
            retrieve_data(source, data_objects, f"output/retrieved/{source}", emit=emit)
            retrieve_data(target, data_objects, f"output/retrieved/{target}", emit=emit)
            meta_diffs = compare_metadata(
                f"output/retrieved/{source}",
                f"output/retrieved/{target}",
                metadata_types=metadata_types,
                emit=emit,
            )
            data_diffs = compare_data(
                f"output/retrieved/{source}",
                f"output/retrieved/{target}",
                data_objects,
                emit=emit,
            )
            all_diffs = meta_diffs + data_diffs
            save_results(all_diffs, DIFF_FILE)
            q.put({
                "level": "quiet",
                "msg": f"Done \u2014 {len(all_diffs)} differences found",
                "done": True,
                "total": len(all_diffs),
            })
        except Exception as e:
            q.put({"level": "error", "msg": str(e), "done": True})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def generate():
        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


def run():
    app.run(debug=True, port=5000)

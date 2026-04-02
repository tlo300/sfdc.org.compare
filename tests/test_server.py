import json
import pytest
import yaml
from unittest.mock import MagicMock, patch
from orgcompare.server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Create a minimal config.yaml in the temp dir
    (tmp_path / "config.yaml").write_text(
        "source_org: DEVRCA\ntarget_org: UATR\n"
        "metadata_types: [ApexClass, Flow]\n"
        "data_objects:\n"
        "  - name: Product2\n    query: SELECT Id FROM Product2\n    external_id: Name\n"
    )
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_get_profiles_empty(client):
    res = client.get("/profiles")
    assert res.status_code == 200
    data = res.get_json()
    assert data == {"profiles": {}}


def test_post_profiles_creates_profile(client):
    res = client.post(
        "/profiles",
        data=json.dumps({"name": "quick", "metadata_types": ["ApexClass"], "data_objects": ["Product2"]}),
        content_type="application/json",
    )
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}
    # verify it is now listed
    res2 = client.get("/profiles")
    profiles = res2.get_json()["profiles"]
    assert "quick" in profiles
    assert profiles["quick"]["metadata_types"] == ["ApexClass"]


def test_post_profiles_missing_name_returns_400(client):
    res = client.post(
        "/profiles",
        data=json.dumps({"metadata_types": ["ApexClass"], "data_objects": []}),
        content_type="application/json",
    )
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_post_profiles_unknown_type_returns_400(client):
    res = client.post(
        "/profiles",
        data=json.dumps({"name": "bad", "metadata_types": ["UnknownType"], "data_objects": []}),
        content_type="application/json",
    )
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_delete_profile(client):
    # create then delete
    client.post(
        "/profiles",
        data=json.dumps({"name": "quick", "metadata_types": ["ApexClass"], "data_objects": []}),
        content_type="application/json",
    )
    res = client.delete("/profiles/quick")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}
    profiles = client.get("/profiles").get_json()["profiles"]
    assert "quick" not in profiles


def test_run_compare_respects_explicit_empty_metadata(client, tmp_path):
    # When metadata_types=[] is sent, the server must not fall back to the full config.
    # retrieve_metadata short-circuits on empty lists (no sf CLI call), and rglob on
    # non-existent dirs returns empty in Python 3.12+, so the run completes with 0 results.
    res = client.post(
        "/api/run-compare",
        data=json.dumps({"metadata_types": [], "data_objects": []}),
        content_type="application/json",
    )
    data = res.get_json()
    # Key assertions: the run succeeds (no crash), returns 0 results (explicit empty
    # selection was respected — full config was NOT substituted).
    assert data["status"] == "ok"
    assert data["total"] == 0


def test_get_discover_returns_cached_false_when_no_file(client):
    res = client.get("/api/discover")
    assert res.status_code == 200
    assert res.get_json() == {"cached": False}


def test_get_discover_returns_cache_when_file_exists(client, tmp_path):
    cache = {"metadata_types": ["ApexClass", "Flow"], "data_objects": ["Account"]}
    (tmp_path / "discovered.json").write_text(__import__("json").dumps(cache))
    res = client.get("/api/discover")
    assert res.status_code == 200
    data = res.get_json()
    assert data["metadata_types"] == ["ApexClass", "Flow"]
    assert data["data_objects"] == ["Account"]


def test_post_discover_calls_run_discovery_and_returns_result(client):
    discovery = {"metadata_types": ["Flow"], "data_objects": ["Contact", "Product2"]}
    with patch("orgcompare.server.run_discovery", return_value=discovery) as mock_disc:
        res = client.post("/api/discover")
    assert res.status_code == 200
    data = res.get_json()
    assert data["metadata_types"] == ["Flow"]
    assert data["data_objects"] == ["Contact", "Product2"]
    mock_disc.assert_called_once()


def test_post_discover_returns_500_on_error(client):
    with patch("orgcompare.server.run_discovery", side_effect=RuntimeError("sf CLI not found")):
        res = client.post("/api/discover")
    assert res.status_code == 500
    assert res.get_json()["status"] == "error"


def test_index_passes_empty_discovered_when_no_cache(client):
    res = client.get("/")
    assert res.status_code == 200
    # Template renders without error — discovered lists are empty
    assert b"OrgCompare" in res.data


def test_run_compare_generates_default_query_for_unknown_object(client):
    with patch("orgcompare.server.retrieve_metadata"), \
         patch("orgcompare.server.retrieve_data") as mock_rd, \
         patch("orgcompare.server.compare_metadata", return_value=[]), \
         patch("orgcompare.server.compare_data", return_value=[]), \
         patch("orgcompare.server.save_results"):
        res = client.post(
            "/api/run-compare",
            data=__import__("json").dumps({"metadata_types": [], "data_objects": ["UnknownObj__c"]}),
            content_type="application/json",
        )
    assert res.status_code == 200
    # Both source + target retrieve_data calls — check the object list in each
    for call in mock_rd.call_args_list:
        objects = call[0][1]
        unknown = next(o for o in objects if o["name"] == "UnknownObj__c")
        assert "FIELDS(ALL)" in unknown["query"]
        assert "LIMIT 200" in unknown["query"]


# --- Org registry endpoint tests ---

def test_get_orgs_bootstraps_from_config(client):
    """GET /api/orgs should bootstrap orgs.yaml from config.yaml and return DEVRCA/UATR."""
    res = client.get("/api/orgs")
    assert res.status_code == 200
    data = res.get_json()
    aliases = [o["alias"] for o in data["orgs"]]
    assert "DEVRCA" in aliases
    assert "UATR" in aliases
    assert data["selection"]["source"] == "DEVRCA"
    assert data["selection"]["target"] == "UATR"


def test_post_org_adds_entry(client):
    res = client.post(
        "/api/orgs",
        data=json.dumps({"alias": "PROD", "name": "Production"}),
        content_type="application/json",
    )
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}
    orgs = client.get("/api/orgs").get_json()["orgs"]
    assert any(o["alias"] == "PROD" for o in orgs)


def test_post_org_missing_alias_returns_400(client):
    res = client.post(
        "/api/orgs",
        data=json.dumps({"name": "No Alias"}),
        content_type="application/json",
    )
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_post_org_duplicate_alias_returns_400(client):
    client.post(
        "/api/orgs",
        data=json.dumps({"alias": "PROD", "name": "Production"}),
        content_type="application/json",
    )
    res = client.post(
        "/api/orgs",
        data=json.dumps({"alias": "PROD", "name": "Production 2"}),
        content_type="application/json",
    )
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_delete_org_removes_entry(client):
    client.post(
        "/api/orgs",
        data=json.dumps({"alias": "PROD", "name": "Production"}),
        content_type="application/json",
    )
    res = client.delete("/api/orgs/PROD")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}
    orgs = client.get("/api/orgs").get_json()["orgs"]
    assert not any(o["alias"] == "PROD" for o in orgs)


def test_patch_org_selection_updates_selection(client):
    res = client.patch(
        "/api/orgs/selection",
        data=json.dumps({"source": "UATR", "target": "DEVRCA"}),
        content_type="application/json",
    )
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}
    sel = client.get("/api/orgs").get_json()["selection"]
    assert sel == {"source": "UATR", "target": "DEVRCA"}


def test_patch_org_selection_unknown_alias_returns_400(client):
    res = client.patch(
        "/api/orgs/selection",
        data=json.dumps({"source": "NOTEXIST", "target": "DEVRCA"}),
        content_type="application/json",
    )
    assert res.status_code == 400
    assert "error" in res.get_json()


# ── POST /api/orgs/login ────────────────────────────────────────────────────

def test_post_login_missing_alias_returns_400(client):
    res = client.post(
        "/api/orgs/login",
        data=json.dumps({"name": "My Org", "instance_url": "https://test.salesforce.com"}),
        content_type="application/json",
    )
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_post_login_missing_name_returns_400(client):
    res = client.post(
        "/api/orgs/login",
        data=json.dumps({"alias": "DEV", "instance_url": "https://test.salesforce.com"}),
        content_type="application/json",
    )
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_post_login_invalid_instance_url_returns_400(client):
    res = client.post(
        "/api/orgs/login",
        data=json.dumps({"alias": "DEV", "name": "Dev", "instance_url": "https://evil.com"}),
        content_type="application/json",
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid instance_url"


def test_post_login_returns_job_id(client):
    from orgcompare.server import _LOGIN_JOBS
    with patch("orgcompare.server.threading.Thread") as mock_thread:
        mock_thread.return_value.start = lambda: None
        res = client.post(
            "/api/orgs/login",
            data=json.dumps({
                "alias": "DEV", "name": "Dev Sandbox",
                "instance_url": "https://test.salesforce.com",
            }),
            content_type="application/json",
        )
    assert res.status_code == 200
    data = res.get_json()
    assert "job_id" in data
    assert len(data["job_id"]) == 36  # UUID format
    del _LOGIN_JOBS[data["job_id"]]


# ── GET /api/orgs/login/status/<job_id> ────────────────────────────────────

def test_login_status_unknown_job_returns_404(client):
    res = client.get("/api/orgs/login/status/nonexistent-id")
    assert res.status_code == 404
    assert "error" in res.get_json()


def test_login_status_returns_running(client):
    from orgcompare.server import _LOGIN_JOBS
    _LOGIN_JOBS["test-running"] = {"status": "running"}
    res = client.get("/api/orgs/login/status/test-running")
    assert res.status_code == 200
    assert res.get_json()["status"] == "running"
    del _LOGIN_JOBS["test-running"]


def test_login_status_returns_done(client):
    from orgcompare.server import _LOGIN_JOBS
    _LOGIN_JOBS["test-done"] = {"status": "done"}
    res = client.get("/api/orgs/login/status/test-done")
    assert res.status_code == 200
    assert res.get_json()["status"] == "done"
    assert "error" not in res.get_json()
    del _LOGIN_JOBS["test-done"]


def test_login_status_returns_error(client):
    from orgcompare.server import _LOGIN_JOBS
    _LOGIN_JOBS["test-error"] = {"status": "error", "error": "Auth cancelled"}
    res = client.get("/api/orgs/login/status/test-error")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "error"
    assert data["error"] == "Auth cancelled"
    del _LOGIN_JOBS["test-error"]


# ── _run_login ──────────────────────────────────────────────────────────────

def test_run_login_success_sets_done(tmp_path, monkeypatch):
    from orgcompare.server import _run_login, _LOGIN_JOBS
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "source_org: A\ntarget_org: B\nmetadata_types: []\ndata_objects: []\n"
    )
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch("orgcompare.server.subprocess.run", return_value=mock_result):
        _run_login("job-ok", "NEWORG", "New Org", "https://test.salesforce.com")
    assert _LOGIN_JOBS["job-ok"]["status"] == "done"
    orgs_file = tmp_path / "orgs.yaml"
    assert orgs_file.exists()
    orgs = yaml.safe_load(orgs_file.read_text())
    assert any(o["alias"] == "NEWORG" for o in orgs["orgs"])
    del _LOGIN_JOBS["job-ok"]


def test_run_login_cli_failure_sets_error(tmp_path, monkeypatch):
    from orgcompare.server import _run_login, _LOGIN_JOBS
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "source_org: A\ntarget_org: B\nmetadata_types: []\ndata_objects: []\n"
    )
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "Authentication failed"
    with patch("orgcompare.server.subprocess.run", return_value=mock_result):
        _run_login("job-fail", "NEWORG", "New Org", "https://test.salesforce.com")
    assert _LOGIN_JOBS["job-fail"]["status"] == "error"
    assert _LOGIN_JOBS["job-fail"]["error"] == "Authentication failed"
    del _LOGIN_JOBS["job-fail"]


def test_run_login_duplicate_alias_sets_error(tmp_path, monkeypatch):
    from orgcompare.server import _run_login, _LOGIN_JOBS
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "source_org: A\ntarget_org: B\nmetadata_types: []\ndata_objects: []\n"
    )
    # Pre-populate orgs.yaml with the alias we'll try to add
    (tmp_path / "orgs.yaml").write_text(
        "orgs:\n- alias: NEWORG\n  name: Existing\nselection:\n  source: ''\n  target: ''\n"
    )
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch("orgcompare.server.subprocess.run", return_value=mock_result):
        _run_login("job-dup", "NEWORG", "New Org", "https://test.salesforce.com")
    assert _LOGIN_JOBS["job-dup"]["status"] == "error"
    assert "already exists" in _LOGIN_JOBS["job-dup"]["error"]
    del _LOGIN_JOBS["job-dup"]


def test_run_login_subprocess_exception_sets_error(tmp_path, monkeypatch):
    from orgcompare.server import _run_login, _LOGIN_JOBS
    monkeypatch.chdir(tmp_path)
    with patch("orgcompare.server.subprocess.run", side_effect=FileNotFoundError("sf not found")):
        _run_login("job-exc", "NEWORG", "New Org", "https://test.salesforce.com")
    assert _LOGIN_JOBS["job-exc"]["status"] == "error"
    assert "sf not found" in _LOGIN_JOBS["job-exc"]["error"]
    del _LOGIN_JOBS["job-exc"]


def test_discover_stream_returns_done_event(client):
    def fake_discovery(org, cache_path, emit=None):
        if emit:
            emit("normal", "test normal message")
        return {"metadata_types": ["ApexClass"], "data_objects": ["Account"]}

    with patch("orgcompare.server.run_discovery", side_effect=fake_discovery), \
         patch("orgcompare.server._load_orgs", return_value={
             "selection": {"source": "DEVRCA", "target": "UATR"}, "orgs": []
         }):
        res = client.get("/api/discover/stream")
        body = res.get_data(as_text=True)
    assert res.status_code == 200
    assert "text/event-stream" in res.content_type
    assert '"done": true' in body or '"done":true' in body
    assert "ApexClass" in body


def test_discover_stream_emits_intermediate_message(client):
    def fake_discovery(org, cache_path, emit=None):
        if emit:
            emit("normal", "Listing all metadata types...")
        return {"metadata_types": [], "data_objects": []}

    with patch("orgcompare.server.run_discovery", side_effect=fake_discovery), \
         patch("orgcompare.server._load_orgs", return_value={
             "selection": {"source": "DEVRCA", "target": "UATR"}, "orgs": []
         }):
        res = client.get("/api/discover/stream")
        body = res.get_data(as_text=True)
    assert "Listing all metadata types" in body


def test_discover_stream_emits_error_event_on_exception(client):
    with patch("orgcompare.server.run_discovery", side_effect=RuntimeError("sf failed")), \
         patch("orgcompare.server._load_orgs", return_value={
             "selection": {"source": "DEVRCA", "target": "UATR"}, "orgs": []
         }):
        res = client.get("/api/discover/stream")
        body = res.get_data(as_text=True)
    assert '"error"' in body
    assert "sf failed" in body


def test_compare_stream_returns_done_event(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "source_org: DEVRCA\ntarget_org: UATR\n"
        "metadata_types: [ApexClass]\n"
        "data_objects:\n  - name: Product2\n    query: SELECT Id FROM Product2\n    external_id: Name\n"
    )
    with patch("orgcompare.server.retrieve_metadata"), \
         patch("orgcompare.server.retrieve_data"), \
         patch("orgcompare.server.compare_metadata", return_value=[]), \
         patch("orgcompare.server.compare_data", return_value=[]), \
         patch("orgcompare.server.save_results"), \
         patch("orgcompare.server._load_orgs", return_value={
             "selection": {"source": "DEVRCA", "target": "UATR"}, "orgs": []
         }):
        params = "metadata_types=%5B%22ApexClass%22%5D&data_objects=%5B%22Product2%22%5D"
        res = client.get(f"/api/compare/stream?{params}")
        body = res.get_data(as_text=True)
    assert res.status_code == 200
    assert "text/event-stream" in res.content_type
    assert '"done": true' in body or '"done":true' in body


def test_compare_stream_emits_error_on_exception(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "source_org: DEVRCA\ntarget_org: UATR\n"
        "metadata_types: [ApexClass]\ndata_objects: []\n"
    )
    with patch("orgcompare.server.retrieve_metadata", side_effect=RuntimeError("retrieve failed")), \
         patch("orgcompare.server._load_orgs", return_value={
             "selection": {"source": "DEVRCA", "target": "UATR"}, "orgs": []
         }):
        res = client.get("/api/compare/stream?metadata_types=%5B%22ApexClass%22%5D&data_objects=%5B%5D")
        body = res.get_data(as_text=True)
    assert '"error"' in body
    assert "retrieve failed" in body

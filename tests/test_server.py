import json
import pytest
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


from unittest.mock import patch


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

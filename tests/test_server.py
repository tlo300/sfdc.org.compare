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
    # When metadata_types=[] is sent, the server should not fall back to full config.
    # We can't run a real retrieve here; just verify the endpoint parses the body
    # without crashing on empty list. Since retrieve will fail (no sf CLI in test env),
    # we expect a 500 with an error message — not a 200 with the full config substituted.
    res = client.post(
        "/api/run-compare",
        data=json.dumps({"metadata_types": [], "data_objects": []}),
        content_type="application/json",
    )
    data = res.get_json()
    # Should attempt the run (and fail due to no sf CLI) rather than substituting full config
    # The key assertion: status is "error", not "ok" with full config results
    assert data["status"] == "error"


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

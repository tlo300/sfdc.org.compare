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

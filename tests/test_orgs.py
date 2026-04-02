import pytest
from orgcompare.orgs import load_orgs, save_orgs, bootstrap_orgs, add_org, remove_org, set_selection


def _write_config(tmp_path, source="DEVRCA", target="UATR"):
    (tmp_path / "config.yaml").write_text(
        f"source_org: {source}\ntarget_org: {target}\n", encoding="utf-8"
    )


def test_load_orgs_returns_defaults_when_file_missing(tmp_path):
    result = load_orgs(str(tmp_path / "orgs.yaml"))
    assert result == {"orgs": [], "selection": {"source": "", "target": ""}}


def test_save_and_load_orgs_roundtrip(tmp_path):
    path = str(tmp_path / "orgs.yaml")
    data = {
        "orgs": [{"alias": "DEV", "name": "Dev Sandbox"}],
        "selection": {"source": "DEV", "target": ""},
    }
    save_orgs(path, data)
    result = load_orgs(path)
    assert result["orgs"] == [{"alias": "DEV", "name": "Dev Sandbox"}]
    assert result["selection"]["source"] == "DEV"


def test_bootstrap_creates_orgs_from_config(tmp_path):
    _write_config(tmp_path)
    orgs_path = str(tmp_path / "orgs.yaml")
    bootstrap_orgs(orgs_path, str(tmp_path / "config.yaml"))
    result = load_orgs(orgs_path)
    assert len(result["orgs"]) == 2
    assert result["orgs"][0]["alias"] == "DEVRCA"
    assert result["orgs"][1]["alias"] == "UATR"
    assert result["selection"] == {"source": "DEVRCA", "target": "UATR"}


def test_bootstrap_does_not_overwrite_existing_file(tmp_path):
    _write_config(tmp_path)
    orgs_path = str(tmp_path / "orgs.yaml")
    save_orgs(orgs_path, {
        "orgs": [{"alias": "PROD", "name": "Production"}],
        "selection": {"source": "PROD", "target": ""},
    })
    bootstrap_orgs(orgs_path, str(tmp_path / "config.yaml"))
    result = load_orgs(orgs_path)
    assert result["orgs"][0]["alias"] == "PROD"


def test_bootstrap_deduplicates_when_source_equals_target(tmp_path):
    _write_config(tmp_path, source="DEV", target="DEV")
    orgs_path = str(tmp_path / "orgs.yaml")
    bootstrap_orgs(orgs_path, str(tmp_path / "config.yaml"))
    result = load_orgs(orgs_path)
    assert len(result["orgs"]) == 1


def test_add_org_appends_entry(tmp_path):
    path = str(tmp_path / "orgs.yaml")
    add_org(path, "DEV", "Dev Sandbox")
    result = load_orgs(path)
    assert result["orgs"] == [{"alias": "DEV", "name": "Dev Sandbox"}]


def test_add_org_raises_on_duplicate_alias(tmp_path):
    path = str(tmp_path / "orgs.yaml")
    add_org(path, "DEV", "Dev Sandbox")
    with pytest.raises(ValueError, match="already exists"):
        add_org(path, "DEV", "Dev Sandbox 2")


def test_remove_org_deletes_entry(tmp_path):
    path = str(tmp_path / "orgs.yaml")
    add_org(path, "DEV", "Dev")
    add_org(path, "UAT", "UAT")
    remove_org(path, "DEV")
    result = load_orgs(path)
    assert len(result["orgs"]) == 1
    assert result["orgs"][0]["alias"] == "UAT"


def test_remove_org_clears_source_selection(tmp_path):
    path = str(tmp_path / "orgs.yaml")
    add_org(path, "DEV", "Dev")
    add_org(path, "UAT", "UAT")
    set_selection(path, "DEV", "UAT")
    remove_org(path, "DEV")
    result = load_orgs(path)
    assert result["selection"]["source"] == ""
    assert result["selection"]["target"] == "UAT"


def test_remove_org_clears_target_selection(tmp_path):
    path = str(tmp_path / "orgs.yaml")
    add_org(path, "DEV", "Dev")
    add_org(path, "UAT", "UAT")
    set_selection(path, "DEV", "UAT")
    remove_org(path, "UAT")
    result = load_orgs(path)
    assert result["selection"]["source"] == "DEV"
    assert result["selection"]["target"] == ""


def test_remove_org_noop_for_unknown_alias(tmp_path):
    path = str(tmp_path / "orgs.yaml")
    add_org(path, "DEV", "Dev")
    remove_org(path, "NOTEXIST")  # should not raise
    assert len(load_orgs(path)["orgs"]) == 1


def test_set_selection_updates_both_slots(tmp_path):
    path = str(tmp_path / "orgs.yaml")
    add_org(path, "DEV", "Dev")
    add_org(path, "UAT", "UAT")
    set_selection(path, "DEV", "UAT")
    result = load_orgs(path)
    assert result["selection"] == {"source": "DEV", "target": "UAT"}


def test_set_selection_raises_for_unknown_source(tmp_path):
    path = str(tmp_path / "orgs.yaml")
    add_org(path, "DEV", "Dev")
    with pytest.raises(ValueError, match="not in registry"):
        set_selection(path, "NOTEXIST", "DEV")


def test_set_selection_raises_for_unknown_target(tmp_path):
    path = str(tmp_path / "orgs.yaml")
    add_org(path, "DEV", "Dev")
    add_org(path, "UAT", "UAT")
    with pytest.raises(ValueError, match="not in registry"):
        set_selection(path, "DEV", "NOTEXIST")


def test_set_selection_allows_empty_strings(tmp_path):
    path = str(tmp_path / "orgs.yaml")
    add_org(path, "DEV", "Dev")
    set_selection(path, "", "")  # should not raise — clearing selection is valid
    result = load_orgs(path)
    assert result["selection"] == {"source": "", "target": ""}

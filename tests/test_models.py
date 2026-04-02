from orgcompare.models import DiffResult


def test_diff_result_to_dict():
    dr = DiffResult(
        category="metadata",
        type="ApexClass",
        name="OrderService",
        status="modified",
        source_value={"apiVersion": "59.0"},
        target_value={"apiVersion": "58.0"},
        diff={"values_changed": {"root['apiVersion']": {"new_value": "59.0", "old_value": "58.0"}}},
    )
    d = dr.to_dict()
    assert d["category"] == "metadata"
    assert d["type"] == "ApexClass"
    assert d["name"] == "OrderService"
    assert d["status"] == "modified"
    assert d["source_value"] == {"apiVersion": "59.0"}
    assert d["diff"]["values_changed"]["root['apiVersion']"]["new_value"] == "59.0"


def test_diff_result_round_trip():
    dr = DiffResult(
        category="data",
        type="Product2",
        name="Enterprise License",
        status="added",
        source_value={"Name": "Enterprise License", "IsActive": True},
        target_value={},
        diff={},
    )
    restored = DiffResult.from_dict(dr.to_dict())
    assert restored.category == dr.category
    assert restored.name == dr.name
    assert restored.source_value == dr.source_value


def test_xml_diff_field_defaults_to_none():
    dr = DiffResult(
        category="metadata", type="ApexClass", name="OrderService",
        status="modified",
        source_value={"apiVersion": "59.0"}, target_value={"apiVersion": "58.0"},
        diff={},
    )
    assert dr.xml_diff is None


def test_xml_diff_field_round_trips():
    dr = DiffResult(
        category="metadata", type="ApexClass", name="OrderService",
        status="modified",
        source_value={}, target_value={}, diff={},
        xml_diff="--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new\n",
    )
    d = dr.to_dict()
    assert d["xml_diff"] == dr.xml_diff
    restored = DiffResult.from_dict(d)
    assert restored.xml_diff == dr.xml_diff


def test_from_dict_without_xml_diff_key():
    """Old serialised diff.json files without xml_diff must still deserialise."""
    d = {
        "category": "metadata", "type": "ApexClass", "name": "OrderService",
        "status": "modified",
        "source_value": {}, "target_value": {}, "diff": {},
    }
    dr = DiffResult.from_dict(d)
    assert dr.xml_diff is None

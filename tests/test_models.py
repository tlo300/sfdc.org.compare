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

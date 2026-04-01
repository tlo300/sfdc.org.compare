from pathlib import Path
from orgcompare.models import DiffResult
from orgcompare.report import generate_html, generate_csv


SAMPLE_RESULTS = [
    DiffResult(
        category="metadata", type="ApexClass", name="OrderService",
        status="modified",
        source_value={"apiVersion": "59.0"},
        target_value={"apiVersion": "58.0"},
        diff={"values_changed": {"root['apiVersion']": {"new_value": "59.0", "old_value": "58.0"}}},
    ),
    DiffResult(
        category="data", type="Product2", name="Enterprise License",
        status="added",
        source_value={"Name": "Enterprise License", "IsActive": True},
        target_value={},
        diff={},
    ),
    DiffResult(
        category="metadata", type="ApexClass", name="UnchangedClass",
        status="identical",
        source_value={"apiVersion": "59.0"},
        target_value={"apiVersion": "59.0"},
        diff={},
    ),
]


def test_generate_html_creates_file(tmp_path):
    out_file = str(tmp_path / "report.html")
    generate_html(SAMPLE_RESULTS, out_file, "DEVRCA", "UATR")
    assert Path(out_file).exists()
    content = Path(out_file).read_text()
    assert "DEVRCA" in content
    assert "UATR" in content


def test_generate_html_excludes_identical_by_default(tmp_path):
    out_file = str(tmp_path / "report.html")
    generate_html(SAMPLE_RESULTS, out_file, "DEVRCA", "UATR")
    content = Path(out_file).read_text()
    assert "UnchangedClass" not in content
    assert "OrderService" in content


def test_generate_html_includes_identical_when_flag_set(tmp_path):
    out_file = str(tmp_path / "report.html")
    generate_html(SAMPLE_RESULTS, out_file, "DEVRCA", "UATR", show_identical=True)
    content = Path(out_file).read_text()
    assert "UnchangedClass" in content


def test_generate_csv_creates_file_per_type(tmp_path):
    generate_csv(SAMPLE_RESULTS, str(tmp_path))
    apex_csv = tmp_path / "ApexClass_diff.csv"
    product_csv = tmp_path / "Product2_diff.csv"
    assert apex_csv.exists()
    assert product_csv.exists()


def test_generate_csv_has_correct_columns(tmp_path):
    generate_csv(SAMPLE_RESULTS, str(tmp_path))
    import csv as csv_module
    with open(tmp_path / "ApexClass_diff.csv") as f:
        reader = csv_module.DictReader(f)
        rows = list(reader)
    assert rows
    assert set(rows[0].keys()) == {"name", "status", "field", "source_value", "target_value"}


def test_generate_csv_excludes_identical(tmp_path):
    generate_csv(SAMPLE_RESULTS, str(tmp_path))
    import csv as csv_module
    with open(tmp_path / "ApexClass_diff.csv") as f:
        content = f.read()
    assert "UnchangedClass" not in content

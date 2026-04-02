"""Re-export the 4 objects that hit the 200-row cap using Bulk API 2.0."""
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import yaml

# RFC 4180-compliant CSV: UTF-8 with BOM (Excel-safe), CRLF line endings,
# comma delimiter, quote all non-numeric values.
_CSV_OPTS: dict = dict(
    index=False,
    encoding="utf-8-sig",
    lineterminator="\r\n",
    quoting=csv.QUOTE_NONNUMERIC,
)

_SF = "sf.cmd" if sys.platform == "win32" else "sf"
_config = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text())
_SOURCE = _config["source_org"]
_TARGET = _config["target_org"]
_OUT = Path(__file__).parent.parent / "output" / "rc_export2"

# Objects that hit the 200-row FIELDS(ALL) cap
OBJECTS = [
    "Product2",
    "ProductSellingModelOption",
    "PricebookEntry",
    "ProductCategoryProduct",
]

_KEY_CANDIDATES = ["Name", "DeveloperName", "MasterLabel", "Id"]

# Fields that differ between orgs for non-meaningful reasons (audit trail, timestamps, Gearset ids)
_AUDIT_FIELDS = {
    "CreatedById", "CreatedDate",
    "LastModifiedById", "LastModifiedDate",
    "LastReferencedDate", "LastViewedDate",
    "SystemModstamp",
    "GearsetExternalId__c",
}

# Field types that can't be queried via Bulk API 2.0
_SKIP_TYPES = {"address", "location", "anytype"}


def get_queryable_fields(obj: str, org: str) -> list[str]:
    """Return list of queryable field names for obj, excluding compound types."""
    result = subprocess.run(
        [_SF, "sobject", "describe", "--sobject", obj, "--target-org", org, "--json"],
        capture_output=True, encoding="utf-8", errors="replace",
    )
    data = json.loads(result.stdout)
    fields = data.get("result", {}).get("fields", [])
    # sf CLI describe JSON doesn't expose a 'queryable' flag; filter by compound type only
    return [
        f["name"] for f in fields
        if f.get("type", "").lower() not in _SKIP_TYPES
        and not f.get("compoundFieldName")  # skip sub-components of compound fields
    ]


def bulk_export(org: str, obj: str, fields: list[str]) -> pd.DataFrame:
    """Export all records for obj from org via Bulk API 2.0, return DataFrame."""
    query = f"SELECT {', '.join(fields)} FROM {obj}"
    print(f"  Bulk exporting {obj} from {org} ({len(fields)} fields)...")
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, dir=_OUT) as tmp:
        tmp_path = Path(tmp.name)
    try:
        result = subprocess.run(
            [
                _SF, "data", "export", "bulk",
                "--query", query,
                "--target-org", org,
                "--result-format", "csv",
                "--output-file", str(tmp_path),
                "--wait", "10",
            ],
            capture_output=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            print(f"    WARN: bulk export failed for {obj} @ {org}: {result.stderr.strip()[:300]}")
            return pd.DataFrame()
        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            print(f"    WARN: empty result for {obj} @ {org}")
            return pd.DataFrame()
        df = pd.read_csv(tmp_path, low_memory=False)
        return df
    finally:
        tmp_path.unlink(missing_ok=True)


def diff_frames(src: pd.DataFrame, tgt: pd.DataFrame) -> pd.DataFrame:
    """Compare src and tgt, returning a diff summary keyed by best natural key."""
    if src.empty and tgt.empty:
        return pd.DataFrame([{"_status": "both empty"}])

    src_cols = set(src.columns) if not src.empty else set()
    tgt_cols = set(tgt.columns) if not tgt.empty else set()
    all_cols = src_cols | tgt_cols

    key = next((c for c in _KEY_CANDIDATES if c in all_cols), None)

    if src.empty:
        return pd.DataFrame([{"_status": f"{_SOURCE} has 0 records, {_TARGET} has {len(tgt)}"}])
    if tgt.empty:
        return pd.DataFrame([{"_status": f"{_SOURCE} has {len(src)} records, {_TARGET} has 0"}])

    if key is None or key == "Id":
        return pd.DataFrame([{"_status": f"{_SOURCE}={len(src)} rows, {_TARGET}={len(tgt)} rows (no cross-org key)"}])

    common_fields = [c for c in sorted(src_cols & tgt_cols) if c not in (key, "Id") and c not in _AUDIT_FIELDS]

    src2 = src.copy()
    tgt2 = tgt.copy()
    if key in src2.columns:
        src2[key] = src2[key].astype(str)
    if key in tgt2.columns:
        tgt2[key] = tgt2[key].astype(str)

    src_keys = set(src2[key]) if key in src2.columns else set()
    tgt_keys = set(tgt2[key]) if key in tgt2.columns else set()

    rows = []
    for k in sorted(src_keys - tgt_keys):
        rows.append({key: k, "_status": f"only_in_{_SOURCE}"})
    for k in sorted(tgt_keys - src_keys):
        rows.append({key: k, "_status": f"only_in_{_TARGET}"})

    src_idx = src2.set_index(key) if key in src2.columns else src2
    tgt_idx = tgt2.set_index(key) if key in tgt2.columns else tgt2
    for k in sorted(src_keys & tgt_keys):
        diffs = []
        for f in common_fields:
            sv = str(src_idx.loc[k, f]) if f in src_idx.columns else "N/A"
            tv = str(tgt_idx.loc[k, f]) if f in tgt_idx.columns else "N/A"
            if sv != tv:
                diffs.append(f"{f}: [{sv}] → [{tv}]")
        if diffs:
            rows.append({key: k, "_status": "field_diff", "_changes": " | ".join(diffs)})

    if not rows:
        rows.append({"_status": f"IDENTICAL — {len(src)} records match on {key}"})

    return pd.DataFrame(rows)


def main():
    _OUT.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {_OUT}\n")

    for obj in OBJECTS:
        print(f"[{obj}]")
        # Describe fields from both orgs; use intersection to avoid "no such column" errors
        src_fields = set(get_queryable_fields(obj, _SOURCE))
        tgt_fields = set(get_queryable_fields(obj, _TARGET))
        common_fields = sorted(src_fields & tgt_fields)
        only_src = sorted(src_fields - tgt_fields)
        only_tgt = sorted(tgt_fields - src_fields)
        print(f"  Fields: {len(common_fields)} shared", end="")
        if only_src:
            print(f", {len(only_src)} only in {_SOURCE}: {only_src}", end="")
        if only_tgt:
            print(f", {len(only_tgt)} only in {_TARGET}: {only_tgt}", end="")
        print()

        src_df = bulk_export(_SOURCE, obj, common_fields)
        tgt_df = bulk_export(_TARGET, obj, common_fields)

        src_csv = _OUT / f"{_SOURCE}_{obj}.csv"
        tgt_csv = _OUT / f"{_TARGET}_{obj}.csv"
        diff_csv = _OUT / f"diff_{obj}.csv"

        src_df.to_csv(src_csv, **_CSV_OPTS)
        tgt_df.to_csv(tgt_csv, **_CSV_OPTS)
        print(f"  Saved {src_csv.name} ({len(src_df)} rows)")
        print(f"  Saved {tgt_csv.name} ({len(tgt_df)} rows)")

        diff_df = diff_frames(src_df, tgt_df)
        diff_df.to_csv(diff_csv, **_CSV_OPTS)
        print(f"  Saved {diff_csv.name} ({len(diff_df)} diff rows)\n")

    print("Done.")


if __name__ == "__main__":
    main()

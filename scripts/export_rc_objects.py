"""Export Revenue Cloud objects from both orgs as CSV and produce per-object diffs."""
import csv
import io
import json
import subprocess
import sys
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

OBJECTS = [
    "ProductSellingModel",
    "ProductRelationshipType",
    "ProductCatalog",
    "Pricing_Table__c",
    "Product2",
    "PriceAdjustmentSchedule",
    "ProductCategory",
    "ProductComponentGroup",
    "ProductClassification",
    "ProductSellingModelOption",
    "PricebookEntry",
    "ProductCategoryProduct",
    "ProductRelatedComponent",
    "ProductClassificationAttr",
    "PriceAdjustmentTier",
    "AttributeBasedAdjustment",
    "AttributeAdjustmentCondition",
    "ProductConfigurationFlow",
]

# Prefer these as natural keys for diffing (order matters — first match wins)
_KEY_CANDIDATES = ["Name", "DeveloperName", "MasterLabel", "Id"]

# Fields that differ between orgs for non-meaningful reasons (audit trail, timestamps, Gearset ids)
_AUDIT_FIELDS = {
    "CreatedById", "CreatedDate",
    "LastModifiedById", "LastModifiedDate",
    "LastReferencedDate", "LastViewedDate",
    "SystemModstamp",
    "GearsetExternalId__c",
}


def query_object(org: str, obj: str) -> pd.DataFrame:
    """Query all fields from obj in org, return DataFrame."""
    print(f"  Querying {obj} from {org}...")
    result = subprocess.run(
        [
            _SF, "data", "query",
            "--query", f"SELECT FIELDS(ALL) FROM {obj} LIMIT 200",
            "--target-org", org,
            "--result-format", "json",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        print(f"    WARN: {obj} @ {org} failed — {result.stderr.strip()[:200]}")
        return pd.DataFrame()
    try:
        data = json.loads(result.stdout)
        records = data.get("result", {}).get("records", [])
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        # Drop SF internal attrs column if present
        df = df.drop(columns=["attributes"], errors="ignore")
        return df
    except Exception as exc:
        print(f"    WARN: parse error for {obj} @ {org}: {exc}")
        return pd.DataFrame()


def diff_frames(src: pd.DataFrame, tgt: pd.DataFrame, obj: str) -> pd.DataFrame:
    """Compare src and tgt DataFrames, returning a diff summary."""
    if src.empty and tgt.empty:
        return pd.DataFrame(columns=["_status"])

    # Determine natural key (pick first candidate present in BOTH non-empty frames)
    key = None
    src_cols = set(src.columns) if not src.empty else set()
    tgt_cols = set(tgt.columns) if not tgt.empty else set()
    all_cols = src_cols | tgt_cols
    for candidate in _KEY_CANDIDATES:
        if candidate in all_cols:
            key = candidate
            break

    # Handle one side empty
    if src.empty:
        rows = [{"_status": f"only_in_{_TARGET}", key or "_key": str(v)}
                for v in (tgt[key] if key and key in tgt.columns else tgt.index)]
        return pd.DataFrame(rows) if rows else pd.DataFrame([{"_status": f"{_TARGET} has {len(tgt)} records, {_SOURCE} has 0"}])
    if tgt.empty:
        rows = [{"_status": f"only_in_{_SOURCE}", key or "_key": str(v)}
                for v in (src[key] if key and key in src.columns else src.index)]
        return pd.DataFrame(rows) if rows else pd.DataFrame([{"_status": f"{_SOURCE} has {len(src)} records, {_TARGET} has 0"}])

    if key is None or key == "Id":
        # No meaningful cross-org key: just report counts
        return pd.DataFrame([{"_status": f"{_SOURCE}={len(src)} rows, {_TARGET}={len(tgt)} rows (no cross-org key for row diff)"}])

    # Align columns
    common_fields = [c for c in sorted(src_cols & tgt_cols) if c not in (key, "Id") and c not in _AUDIT_FIELDS]

    src2 = src.copy()
    tgt2 = tgt.copy()
    # Only assign key column if it exists in the frame
    if key in src2.columns:
        src2[key] = src2[key].astype(str)
    if key in tgt2.columns:
        tgt2[key] = tgt2[key].astype(str)

    src_keys = set(src2[key]) if key in src2.columns else set()
    tgt_keys = set(tgt2[key]) if key in tgt2.columns else set()

    rows = []

    # Only in source
    for k in sorted(src_keys - tgt_keys):
        rows.append({key: k, "_status": f"only_in_{_SOURCE}"})

    # Only in target
    for k in sorted(tgt_keys - src_keys):
        rows.append({key: k, "_status": f"only_in_{_TARGET}"})

    # In both — check field differences
    src_idx = src2.set_index(key)
    tgt_idx = tgt2.set_index(key)
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
        src_df = query_object(_SOURCE, obj)
        tgt_df = query_object(_TARGET, obj)

        src_csv = _OUT / f"{_SOURCE}_{obj}.csv"
        tgt_csv = _OUT / f"{_TARGET}_{obj}.csv"
        diff_csv = _OUT / f"diff_{obj}.csv"

        src_df.to_csv(src_csv, **_CSV_OPTS)
        tgt_df.to_csv(tgt_csv, **_CSV_OPTS)
        cap_warn = " *** HIT 200-ROW CAP — data is truncated ***" if len(src_df) == 200 else ""
        print(f"  Saved {src_csv.name} ({len(src_df)} rows){cap_warn}")
        cap_warn = " *** HIT 200-ROW CAP — data is truncated ***" if len(tgt_df) == 200 else ""
        print(f"  Saved {tgt_csv.name} ({len(tgt_df)} rows){cap_warn}")

        diff_df = diff_frames(src_df, tgt_df, obj)
        diff_df.to_csv(diff_csv, **_CSV_OPTS)
        print(f"  Saved {diff_csv.name} ({len(diff_df)} diff rows)\n")

    print("Done.")


if __name__ == "__main__":
    main()

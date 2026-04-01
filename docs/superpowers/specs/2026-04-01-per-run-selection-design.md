# Per-Run Selection Design Spec
**Date:** 2026-04-01  
**Status:** Approved  
**Extends:** `2026-04-01-orgcompare-design.md`

## Overview

Extend OrgCompare to support per-run selection of which metadata types and data objects to include. Users can define reusable named profiles, select them via CLI flag or the web UI, and save new profiles from the web UI. The existing full-run behavior (no selection specified) is unchanged.

---

## Section 1: Profiles

### `profiles.yaml`

A new file alongside `config.yaml`. `config.yaml` is never modified by this feature.

```yaml
profiles:
  quick:
    metadata_types: [ApexClass, Flow]
    data_objects: [Product2]
  revenue-cloud:
    metadata_types: [CustomObject, CustomField, Flow]
    data_objects: [Product2, Pricebook2, PricebookEntry]
```

- `metadata_types` entries must exist in `config.yaml` `metadata_types` master list
- `data_objects` entries must exist in `config.yaml` `data_objects` names
- Validation happens at load time in `profiles.py`; unknown entries raise a clear error

### `orgcompare/profiles.py`

Responsibilities: load, save, list, and validate profiles.

```python
def load_profiles(profiles_path: str) -> dict          # returns {name: {metadata_types, data_objects}}
def save_profile(profiles_path: str, name: str, metadata_types: list, data_objects: list) -> None
def delete_profile(profiles_path: str, name: str) -> None
def validate_profile(profile: dict, config: dict) -> None  # raises ValueError on unknown entries
```

`profiles.yaml` is created empty (`profiles: {}`) if it does not exist.

### Effective selection resolution (applied in `main.py`)

| Flags passed | Effective selection |
|---|---|
| `--metadata X,Y --objects A` | Those lists exactly (ad hoc) |
| `--profile quick` | Loaded from `profiles.yaml` |
| Neither | Full master lists from `config.yaml` (existing behavior) |

`--metadata`/`--objects` and `--profile` are mutually exclusive; passing both is an error.

---

## Section 2: CLI (`main.py`)

Two optional flags, applicable to `retrieve` and `compare` commands:

```
python main.py retrieve
python main.py retrieve --profile quick
python main.py retrieve --metadata ApexClass,Flow --objects Product2

python main.py retrieve compare report                      # chaining — flags apply to all steps
python main.py retrieve compare report --profile quick
```

`main.py` currently uses a simple `sys.argv` positional loop with no flag parsing. Adding `--profile`, `--metadata`, and `--objects` requires switching to `argparse`. Commands remain positional (`retrieve`, `compare`, etc.); the flags are added as optional arguments parsed before the command loop.

`main.py` resolves the effective `metadata_types` and `data_objects` lists once at startup, then passes them through to:
- `retrieve_metadata(org_alias, metadata_types, output_dir)` — no change to signature
- `retrieve_data(org_alias, data_objects, output_dir)` — no change to signature
- `compare_data(source_dir, target_dir, data_objects)` — no change to signature
- `compare_metadata(source_dir, target_dir, metadata_types=None)` — add optional filter (see below)

### `compare_metadata` addition

Add an optional `metadata_types: list | None = None` parameter. When provided, only files whose inferred type is in the list are included in the diff. When `None`, all files are included (existing behavior).

---

## Section 3: Web UI

### Pre-run selection panel

Added above the existing diff list in `templates/ui.html`:

```
┌─────────────────────────────────────────────────────┐
│  OrgCompare: DEVRCA → UATR                          │
├─────────────────────────────────────────────────────┤
│ Profile: [revenue-cloud ▼]  [Save current as...]    │
│                                                     │
│ Metadata:  [✓] ApexClass  [✓] Flow  [ ] PermSet... │
│ Data:      [✓] Product2   [✓] Pricebook2  ...      │
│                                                     │
│                              [Run Compare]          │
├─────────────────────────────────────────────────────┤
│ ... existing diff list + deploy checkboxes ...      │
└─────────────────────────────────────────────────────┘
```

**Behaviour:**
- Dropdown lists saved profile names from `profiles.yaml` plus a "Custom" option
- Selecting a profile pre-fills the checkboxes client-side (JS, no page reload)
- Editing any checkbox switches the dropdown to "Custom"
- "Save current as..." prompts for a name → `POST /profiles` → persists to `profiles.yaml`; dropdown updates
- "Run Compare" POSTs the current checkbox state; server resolves the selection and runs retrieve + compare with that subset, then refreshes the diff list on completion

### New Flask endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/profiles` | Returns `{profiles: {name: {metadata_types, data_objects}}}` |
| `POST` | `/profiles` | Body: `{name, metadata_types, data_objects}` — create or overwrite profile (silently replaces if name already exists) |
| `DELETE` | `/profiles/<name>` | Delete a named profile |

The existing `POST /api/run-compare` endpoint gains two optional body fields: `metadata_types: list` and `data_objects: list`. If absent, falls back to full config (existing behavior).

The `GET /` route currently passes `source_org`, `target_org`, `results`, and `summary` to the template. It must also pass `metadata_types` (list of strings) and `data_objects` (list of `{name}` dicts) from the master config so the pre-run selection panel can render the checkboxes.

---

## File Impact Summary

| File | Change |
|---|---|
| `profiles.yaml` | **New** — profile storage |
| `orgcompare/profiles.py` | **New** — load/save/validate profiles |
| `main.py` | **New** (not yet written) — add `--profile`, `--metadata`, `--objects` flags |
| `orgcompare/compare.py` | **Small addition** — optional `metadata_types` filter in `compare_metadata` |
| `orgcompare/server.py` | **Extended** — 3 new endpoints, `POST /run` accepts selection |
| `templates/ui.html` | **Extended** — pre-run selection panel |
| `config.yaml` | **No change** |
| `retrieve.py`, `report.py`, `deploy.py`, `models.py` | **No change** |

---

## Field Selection Within Objects

Selecting a data object includes **all fields** as defined by that object's `query` in `config.yaml`. There is no per-field sub-selection — the query is used as-is. To change which fields are retrieved for an object, edit its query in `config.yaml`.

---

## Out of Scope

- Profile sharing across machines (profiles.yaml is local)
- Profile versioning or history

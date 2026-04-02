# Org Registry & Selection Design

**Date:** 2026-04-02
**Status:** Approved

## Problem

Source and target orgs are hardcoded in `config.yaml`. To compare a different pair of orgs you must manually edit the file. There is no UI to manage multiple orgs, swap source/target, or remember the last selection across sessions.

## Goals

- Store a list of named Salesforce CLI orgs locally (outside git)
- Select source and target from that list in the UI
- Persist the last selection across Flask restarts
- Swap source and target with a single click
- Add and remove orgs via a modal in the UI

## Out of Scope

- Authenticating new orgs from the UI (use `sf org login` separately)
- Syncing org selection back to `config.yaml`
- CLI flags for `main.py` to select orgs dynamically

---

## Storage: `orgs.yaml`

A git-ignored file in the project root. Stores the org registry and active selection.

```yaml
orgs:
  - alias: DEVRCA
    name: "Dev Sandbox - Revenue Cloud"
  - alias: UATR
    name: "UAT Sandbox"

selection:
  source: DEVRCA
  target: UATR
```

**Bootstrap:** If `orgs.yaml` does not exist when the server starts, it is auto-created from `config.yaml`'s `source_org` / `target_org` fields (alias = value, name = value).

**Relationship to `config.yaml`:** `config.yaml` remains unchanged and continues to be used by the CLI (`main.py`) and by the server for `metadata_types` and `data_objects`. The Flask server reads `source_org` / `target_org` from `orgs.yaml` only.

`.gitignore` gets `orgs.yaml` added.

---

## Backend: `orgcompare/orgs.py`

New module. Pure file I/O, no Flask dependency.

| Function | Signature | Description |
|---|---|---|
| `load_orgs` | `(path: str) -> dict` | Read `orgs.yaml`, return `{orgs, selection}`. Returns empty defaults if file missing. |
| `save_orgs` | `(path: str, data: dict) -> None` | Write `orgs.yaml` atomically. |
| `bootstrap_orgs` | `(orgs_path: str, config_path: str) -> None` | Create `orgs.yaml` from `config.yaml` if `orgs.yaml` is absent. |
| `add_org` | `(path: str, alias: str, name: str) -> None` | Append org; error if alias already exists. |
| `remove_org` | `(path: str, alias: str) -> None` | Remove org by alias; clear selection if it was source or target. |
| `set_selection` | `(path: str, source: str, target: str) -> None` | Update `selection`; error if alias not in registry. |

---

## API Endpoints (new, in `server.py`)

| Method | Path | Body | Response |
|---|---|---|---|
| `GET` | `/api/orgs` | — | `{orgs: [{alias, name}], selection: {source, target}}` |
| `POST` | `/api/orgs` | `{alias, name}` | `{status: "ok"}` or 400 |
| `DELETE` | `/api/orgs/<alias>` | — | `{status: "ok"}` |
| `PATCH` | `/api/orgs/selection` | `{source, target}` | `{status: "ok"}` or 400 |

---

## Modified Endpoints

- `index()` — reads source/target from `orgs.yaml` (via `load_orgs`) instead of `config.yaml`
- `run_compare()` — reads source/target from `orgs.yaml`
- `deploy()` — reads target from `orgs.yaml`
- `post_discover()` — reads source from `orgs.yaml`

`_load_config()` is unchanged; all other config (metadata types, data objects) still comes from `config.yaml`.

---

## UI Changes (`templates/ui.html`)

### `<h1>` header

Change from `OrgCompare: {{ source_org }} → {{ target_org }}` to simply `OrgCompare`. Org names are shown in the dropdowns.

### Top panel — new "Orgs" row

Added as the first row in `.top-panel`, above the existing Profile row:

```
Orgs:  Source: [DEVRCA - Dev Sandbox ▼]  ⇄  Target: [UATR - UAT Sandbox ▼]   [Manage Orgs]
```

- **Source dropdown** (`#source-select`): populated from `/api/orgs`, option text is `"alias — name"`
- **Target dropdown** (`#target-select`): same population
- **⇄ swap button**: swaps the two dropdown values, then calls `PATCH /api/orgs/selection`
- **Manage Orgs button**: opens the modal

Dropdown `onchange` handler calls `PATCH /api/orgs/selection` immediately.

### Manage Orgs modal (`#orgs-modal`)

- Lists all saved orgs: `alias — name` with a [Remove] button per row
- Add org form: alias input + name input + [Add] button
- Closing the modal refreshes the dropdowns from `/api/orgs`
- Removing an org that is currently selected: modal warns, selection clears to first available org

### Page load

On `DOMContentLoaded`:
1. `GET /api/orgs`
2. Populate both dropdowns
3. Set selected options to match `selection.source` / `selection.target`

No localStorage used — server is the single source of truth.

---

## File Changes Summary

| File | Change |
|---|---|
| `orgcompare/orgs.py` | New module |
| `orgcompare/server.py` | Bootstrap call on startup; new 4 endpoints; update `index`, `run_compare`, `deploy`, `post_discover` |
| `templates/ui.html` | Add Orgs row, Manage Orgs modal, page-load JS, swap/change handlers |
| `.gitignore` | Add `orgs.yaml` |
| `orgs.yaml` | Auto-created locally; never committed |

---

## Error Cases

- **Alias not in registry when setting selection:** 400 response, orgs.yaml unchanged
- **Duplicate alias on add:** 400 response
- **Removing selected org:** server clears that slot to empty string; UI shows warning and prompts re-selection before compare is enabled
- **`orgs.yaml` missing at request time:** bootstrap from `config.yaml`; if `config.yaml` also missing, return 500 with clear message

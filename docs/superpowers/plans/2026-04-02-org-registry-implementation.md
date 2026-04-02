# Org Registry & Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a git-ignored `orgs.yaml` registry so the Flask UI can store named Salesforce CLI orgs, select source/target from dropdowns, swap them with one click, and persist the selection across sessions.

**Architecture:** New `orgcompare/orgs.py` handles all file I/O (no Flask dependency). `server.py` bootstraps `orgs.yaml` from `config.yaml` on first access, exposes four new REST endpoints, and updates four existing endpoints to read source/target from `orgs.yaml` instead of `config.yaml`. The UI gets an Orgs row in the top panel and a Manage Orgs modal.

**Tech Stack:** Python 3.14, PyYAML, Flask, vanilla JS (no new dependencies)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `orgcompare/orgs.py` | Create | Pure file I/O for org registry |
| `tests/test_orgs.py` | Create | Unit tests for orgs.py |
| `orgcompare/server.py` | Modify | Bootstrap helper, 4 new endpoints, update 4 existing |
| `tests/test_server.py` | Modify | Add tests for new org endpoints |
| `templates/ui.html` | Modify | Orgs row, Manage Orgs modal, JS handlers |
| `.gitignore` | Modify | Add `orgs.yaml` |

---

## Task 1: `orgcompare/orgs.py` module

**Files:**
- Create: `orgcompare/orgs.py`
- Create: `tests/test_orgs.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orgs.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd c:\Users\twanv\SalesforceProjects\OrgCompare
.venv/Scripts/python -m pytest tests/test_orgs.py -v
```

Expected: `ModuleNotFoundError: No module named 'orgcompare.orgs'`

- [ ] **Step 3: Create `orgcompare/orgs.py`**

```python
"""Org registry — load, save, and manage named Salesforce CLI orgs."""
import yaml
from pathlib import Path


def load_orgs(path: str) -> dict:
    """Return {orgs, selection} from orgs.yaml. Returns empty defaults if file missing."""
    p = Path(path)
    if not p.exists():
        return {"orgs": [], "selection": {"source": "", "target": ""}}
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {
        "orgs": data.get("orgs") or [],
        "selection": data.get("selection") or {"source": "", "target": ""},
    }


def save_orgs(path: str, data: dict) -> None:
    """Write data to orgs.yaml."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def bootstrap_orgs(orgs_path: str, config_path: str) -> None:
    """Create orgs.yaml from config.yaml source_org/target_org if orgs.yaml is absent."""
    if Path(orgs_path).exists():
        return
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    source = config.get("source_org", "")
    target = config.get("target_org", "")
    seen: set = set()
    orgs = []
    for alias in [source, target]:
        if alias and alias not in seen:
            orgs.append({"alias": alias, "name": alias})
            seen.add(alias)
    save_orgs(orgs_path, {
        "orgs": orgs,
        "selection": {"source": source, "target": target},
    })


def add_org(path: str, alias: str, name: str) -> None:
    """Append org to registry. Raises ValueError if alias already exists."""
    data = load_orgs(path)
    if any(o["alias"] == alias for o in data["orgs"]):
        raise ValueError(f"Org '{alias}' already exists")
    data["orgs"].append({"alias": alias, "name": name})
    save_orgs(path, data)


def remove_org(path: str, alias: str) -> None:
    """Remove org by alias. Clears selection slots that referenced this alias."""
    data = load_orgs(path)
    data["orgs"] = [o for o in data["orgs"] if o["alias"] != alias]
    sel = data.setdefault("selection", {"source": "", "target": ""})
    if sel.get("source") == alias:
        sel["source"] = ""
    if sel.get("target") == alias:
        sel["target"] = ""
    save_orgs(path, data)


def set_selection(path: str, source: str, target: str) -> None:
    """Update active source/target. Empty strings are allowed (clears the slot).
    Raises ValueError if a non-empty alias is not in the registry.
    """
    data = load_orgs(path)
    aliases = {o["alias"] for o in data["orgs"]}
    if source and source not in aliases:
        raise ValueError(f"Org '{source}' not in registry")
    if target and target not in aliases:
        raise ValueError(f"Org '{target}' not in registry")
    data["selection"] = {"source": source, "target": target}
    save_orgs(path, data)
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv/Scripts/python -m pytest tests/test_orgs.py -v
```

Expected: all 16 tests pass.

- [ ] **Step 5: Commit**

```bash
git add orgcompare/orgs.py tests/test_orgs.py
git commit -m "feat: add orgcompare/orgs.py registry module with tests"
```

---

## Task 2: Add `orgs.yaml` to `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add the entry**

Open `.gitignore` and append `orgs.yaml` after the existing `profiles.yaml` line:

```
profiles.yaml
orgs.yaml
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: git-ignore orgs.yaml"
```

---

## Task 3: Update `server.py` — new endpoints and modified existing endpoints

**Files:**
- Modify: `orgcompare/server.py`
- Modify: `tests/test_server.py`

### 3a — Write new server tests first

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_server.py`:

```python
# --- Org registry endpoint tests ---

def test_get_orgs_bootstraps_from_config(client):
    """GET /api/orgs should bootstrap orgs.yaml from config.yaml and return DEVRCA/UATR."""
    res = client.get("/api/orgs")
    assert res.status_code == 200
    data = res.get_json()
    aliases = [o["alias"] for o in data["orgs"]]
    assert "DEVRCA" in aliases
    assert "UATR" in aliases
    assert data["selection"]["source"] == "DEVRCA"
    assert data["selection"]["target"] == "UATR"


def test_post_org_adds_entry(client):
    res = client.post(
        "/api/orgs",
        data=json.dumps({"alias": "PROD", "name": "Production"}),
        content_type="application/json",
    )
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}
    orgs = client.get("/api/orgs").get_json()["orgs"]
    assert any(o["alias"] == "PROD" for o in orgs)


def test_post_org_missing_alias_returns_400(client):
    res = client.post(
        "/api/orgs",
        data=json.dumps({"name": "No Alias"}),
        content_type="application/json",
    )
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_post_org_duplicate_alias_returns_400(client):
    client.post(
        "/api/orgs",
        data=json.dumps({"alias": "PROD", "name": "Production"}),
        content_type="application/json",
    )
    res = client.post(
        "/api/orgs",
        data=json.dumps({"alias": "PROD", "name": "Production 2"}),
        content_type="application/json",
    )
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_delete_org_removes_entry(client):
    client.post(
        "/api/orgs",
        data=json.dumps({"alias": "PROD", "name": "Production"}),
        content_type="application/json",
    )
    res = client.delete("/api/orgs/PROD")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}
    orgs = client.get("/api/orgs").get_json()["orgs"]
    assert not any(o["alias"] == "PROD" for o in orgs)


def test_patch_org_selection_updates_selection(client):
    res = client.patch(
        "/api/orgs/selection",
        data=json.dumps({"source": "UATR", "target": "DEVRCA"}),
        content_type="application/json",
    )
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}
    sel = client.get("/api/orgs").get_json()["selection"]
    assert sel == {"source": "UATR", "target": "DEVRCA"}


def test_patch_org_selection_unknown_alias_returns_400(client):
    res = client.patch(
        "/api/orgs/selection",
        data=json.dumps({"source": "NOTEXIST", "target": "DEVRCA"}),
        content_type="application/json",
    )
    assert res.status_code == 400
    assert "error" in res.get_json()
```

- [ ] **Step 2: Run tests to confirm they fail**

```
.venv/Scripts/python -m pytest tests/test_server.py -k "org" -v
```

Expected: `404 NOT FOUND` or attribute errors on the new endpoints.

### 3b — Update `server.py`

- [ ] **Step 3: Replace the imports block and constants at the top of `server.py`**

Replace the current import section and constants (lines 1–18):

```python
import yaml
from collections import defaultdict
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from orgcompare.compare import compare_data, compare_metadata, load_results, save_results
from orgcompare.deploy import deploy_data, deploy_metadata
from orgcompare.discover import load_discovery_cache, run_discovery
from orgcompare.orgs import add_org, bootstrap_orgs, load_orgs, remove_org, set_selection
from orgcompare.profiles import delete_profile, load_profiles, save_profile, validate_profile
from orgcompare.retrieve import retrieve_data, retrieve_metadata

_TEMPLATES_DIR = str(Path(__file__).parent.parent / "templates")
app = Flask(__name__, template_folder=_TEMPLATES_DIR)
app.config["TEMPLATES_AUTO_RELOAD"] = True
DIFF_FILE = "output/reports/diff.json"
PROFILES_FILE = "profiles.yaml"
DISCOVERY_FILE = "discovered.json"
ORGS_FILE = "orgs.yaml"
```

- [ ] **Step 4: Add `_load_orgs()` helper after `_load_config()`**

Insert after the `_load_config` function (after line 30 in the current file):

```python
def _load_orgs() -> dict:
    """Bootstrap orgs.yaml from config.yaml if absent, then return orgs data."""
    bootstrap_orgs(ORGS_FILE, "config.yaml")
    return load_orgs(ORGS_FILE)
```

- [ ] **Step 5: Update `index()` to use `_load_orgs()`**

Replace the current `index()` function:

```python
@app.route("/")
def index():
    config = _load_config()
    orgs_data = _load_orgs()
    discovered = load_discovery_cache(DISCOVERY_FILE)
    return render_template(
        "ui.html",
        source_org=orgs_data["selection"]["source"],
        target_org=orgs_data["selection"]["target"],
        discovered_metadata=discovered.get("metadata_types", []),
        discovered_objects=discovered.get("data_objects", []),
    )
```

- [ ] **Step 6: Update `run_compare()` to read source/target from `_load_orgs()`**

Replace only the first two lines inside `run_compare()` that set `source` and `target`:

Current:
```python
    config = _load_config()
    source = config["source_org"]
    target = config["target_org"]
```

Replace with:
```python
    config = _load_config()
    orgs_data = _load_orgs()
    source = orgs_data["selection"]["source"]
    target = orgs_data["selection"]["target"]
```

- [ ] **Step 7: Update `deploy()` to read target from `_load_orgs()`**

Replace only the `target = config["target_org"]` line inside `deploy()`:

Current:
```python
    config = _load_config()
    target = config["target_org"]
```

Replace with:
```python
    config = _load_config()
    target = _load_orgs()["selection"]["target"]
```

- [ ] **Step 8: Update `post_discover()` to read source from `_load_orgs()`**

Replace the current `post_discover()` function:

```python
@app.route("/api/discover", methods=["POST"])
def post_discover():
    try:
        result = run_discovery(_load_orgs()["selection"]["source"], DISCOVERY_FILE)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
```

- [ ] **Step 9: Add the four new org endpoints**

Add these four functions after the `delete_profile_endpoint` function and before `get_results`:

```python
@app.route("/api/orgs", methods=["GET"])
def get_orgs():
    return jsonify(_load_orgs())


@app.route("/api/orgs", methods=["POST"])
def post_org():
    body = request.get_json(silent=True) or {}
    alias = (body.get("alias") or "").strip()
    name = (body.get("name") or "").strip()
    if not alias or not name:
        return jsonify({"error": "alias and name are required"}), 400
    try:
        add_org(ORGS_FILE, alias, name)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"status": "ok"})


@app.route("/api/orgs/selection", methods=["PATCH"])
def patch_org_selection():
    body = request.get_json(silent=True) or {}
    source = body.get("source", "")
    target = body.get("target", "")
    try:
        set_selection(ORGS_FILE, source, target)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"status": "ok"})


@app.route("/api/orgs/<alias>", methods=["DELETE"])
def delete_org(alias: str):
    remove_org(ORGS_FILE, alias)
    return jsonify({"status": "ok"})
```

**Important:** Define `/api/orgs/selection` (PATCH) before `/api/orgs/<alias>` (DELETE) as shown above. Flask matches exact paths before variable rules for different HTTP methods, but ordering makes the intent explicit.

- [ ] **Step 10: Run all server tests**

```
.venv/Scripts/python -m pytest tests/test_server.py -v
```

Expected: all tests pass (including the 7 new org tests and all existing tests).

- [ ] **Step 11: Commit**

```bash
git add orgcompare/server.py tests/test_server.py
git commit -m "feat: add org registry endpoints and wire source/target from orgs.yaml"
```

---

## Task 4: Update `templates/ui.html` — Orgs row, modal, and JS

**Files:**
- Modify: `templates/ui.html`

- [ ] **Step 1: Update the `<h1>` tag**

In `templates/ui.html` at line 88, replace:

```html
  <h1>OrgCompare: {{ source_org }} &rarr; {{ target_org }}</h1>
```

With:

```html
  <h1>OrgCompare</h1>
```

- [ ] **Step 2: Add the Orgs row to the top panel**

In `templates/ui.html`, find the `.top-panel` div (around line 91). Insert the following as the **first** `selection-row` inside it, before the existing Profile row:

```html
    <div class="selection-row">
      <label>Orgs:</label>
      <label style="font-size:13px;color:#555;">Source:</label>
      <select id="source-select" onchange="saveOrgSelection()"></select>
      <button class="btn-secondary" onclick="swapOrgs()" title="Swap source and target">&#8644;</button>
      <label style="font-size:13px;color:#555;">Target:</label>
      <select id="target-select" onchange="saveOrgSelection()"></select>
      <button class="btn-secondary" onclick="openOrgsModal()">Manage Orgs</button>
    </div>
```

The top panel should now look like:
```html
  <div class="top-panel">
    <div class="selection-row">
      <label>Orgs:</label>
      ... (new row) ...
    </div>
    <div class="selection-row">
      <label>Profile:</label>
      ... (existing row) ...
    </div>
    <div class="panel-actions">
      ...
    </div>
  </div>
```

- [ ] **Step 3: Add the Manage Orgs modal**

Insert the following HTML block immediately before the `<script>` tag (just before line 675 in the current file):

```html
  <!-- Manage Orgs Modal -->
  <div id="orgs-modal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.4); z-index:1000; align-items:center; justify-content:center;">
    <div style="background:white; border-radius:6px; padding:24px; min-width:400px; max-width:560px; box-shadow:0 4px 20px rgba(0,0,0,0.2);">
      <h3 style="margin:0 0 16px;">Manage Orgs</h3>
      <table style="width:100%; border-collapse:collapse; margin-bottom:16px;">
        <thead>
          <tr>
            <th style="text-align:left; padding:6px 8px; background:#f0f0f0; font-weight:bold;">Alias</th>
            <th style="text-align:left; padding:6px 8px; background:#f0f0f0; font-weight:bold;">Name</th>
            <th style="padding:6px 8px; background:#f0f0f0;"></th>
          </tr>
        </thead>
        <tbody id="orgs-list"></tbody>
      </table>
      <div style="display:flex; gap:8px; align-items:center; margin-bottom:16px; flex-wrap:wrap;">
        <input id="new-org-alias" type="text" placeholder="Alias (e.g. DEVRCA)" style="padding:5px 8px; border:1px solid #ccc; border-radius:4px; font-size:14px; width:140px;">
        <input id="new-org-name" type="text" placeholder="Friendly name" style="padding:5px 8px; border:1px solid #ccc; border-radius:4px; font-size:14px; flex:1; min-width:140px;">
        <button class="btn-primary" onclick="addOrg()">Add</button>
      </div>
      <div style="text-align:right;">
        <button class="btn-secondary" onclick="closeOrgsModal()">Close</button>
      </div>
    </div>
  </div>
```

- [ ] **Step 4: Add org JS functions to the `<script>` block**

In the `<script>` block, find the `// --- Profiles ---` comment (around line 312). Insert the following **before** that comment:

```javascript
    // --- Org selection ---
    let orgsData = { orgs: [], selection: { source: '', target: '' } };

    async function loadOrgsIntoDropdowns() {
      try {
        const res = await fetch('/api/orgs');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        orgsData = await res.json();
        _populateOrgDropdowns();
      } catch (e) {
        showStatus(`Could not load orgs: ${e.message}`, false);
      }
    }

    function _populateOrgDropdowns() {
      ['source-select', 'target-select'].forEach((id, idx) => {
        const sel = document.getElementById(id);
        sel.innerHTML = '';
        orgsData.orgs.forEach(org => {
          const opt = document.createElement('option');
          opt.value = org.alias;
          opt.textContent = `${org.alias} \u2014 ${org.name}`;
          sel.appendChild(opt);
        });
        sel.value = idx === 0 ? orgsData.selection.source : orgsData.selection.target;
      });
    }

    async function saveOrgSelection() {
      const source = document.getElementById('source-select').value;
      const target = document.getElementById('target-select').value;
      await fetch('/api/orgs/selection', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source, target }),
      });
    }

    function swapOrgs() {
      const sourceEl = document.getElementById('source-select');
      const targetEl = document.getElementById('target-select');
      const tmp = sourceEl.value;
      sourceEl.value = targetEl.value;
      targetEl.value = tmp;
      saveOrgSelection();
    }

    function openOrgsModal() {
      _renderOrgsList();
      document.getElementById('orgs-modal').style.display = 'flex';
    }

    function closeOrgsModal() {
      document.getElementById('orgs-modal').style.display = 'none';
      loadOrgsIntoDropdowns();
    }

    function _renderOrgsList() {
      const tbody = document.getElementById('orgs-list');
      tbody.innerHTML = orgsData.orgs.map(org =>
        `<tr>
          <td style="padding:6px 8px; border-bottom:1px solid #eee;">${escHtml(org.alias)}</td>
          <td style="padding:6px 8px; border-bottom:1px solid #eee;">${escHtml(org.name)}</td>
          <td style="padding:6px 8px; border-bottom:1px solid #eee; text-align:right;">
            <button class="btn-warning" style="font-size:12px; padding:3px 8px;" onclick="removeOrg('${escHtml(org.alias)}')">Remove</button>
          </td>
        </tr>`
      ).join('');
    }

    async function addOrg() {
      const alias = document.getElementById('new-org-alias').value.trim();
      const name = document.getElementById('new-org-name').value.trim();
      if (!alias || !name) { showStatus('Alias and name are required.', false); return; }
      const res = await fetch('/api/orgs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alias, name }),
      });
      const data = await res.json();
      if (data.status === 'ok') {
        document.getElementById('new-org-alias').value = '';
        document.getElementById('new-org-name').value = '';
        await loadOrgsIntoDropdowns();
        _renderOrgsList();
      } else {
        showStatus(`Error: ${data.error}`, false);
      }
    }

    async function removeOrg(alias) {
      const source = document.getElementById('source-select').value;
      const target = document.getElementById('target-select').value;
      if (alias === source || alias === target) {
        if (!confirm(`'${alias}' is currently selected. Remove anyway?`)) return;
      }
      await fetch(`/api/orgs/${encodeURIComponent(alias)}`, { method: 'DELETE' });
      await loadOrgsIntoDropdowns();
      _renderOrgsList();
    }

```

- [ ] **Step 5: Add `loadOrgsIntoDropdowns()` to the init section**

Find the `// --- Init ---` comment near the bottom of the `<script>` block (around line 671). Update it:

Current:
```javascript
    // --- Init ---
    loadProfilesIntoDropdown();
    // Clear any browser-restored checkbox state
    document.querySelectorAll('.meta-check, .obj-check').forEach(cb => { cb.checked = false; });
```

Replace with:
```javascript
    // --- Init ---
    loadOrgsIntoDropdowns();
    loadProfilesIntoDropdown();
    // Clear any browser-restored checkbox state
    document.querySelectorAll('.meta-check, .obj-check').forEach(cb => { cb.checked = false; });
```

- [ ] **Step 6: Run the full test suite**

```
.venv/Scripts/python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Smoke test in the browser**

```
.venv/Scripts/python main.py serve
```

Open `http://localhost:5000` and verify:
- `<h1>` shows "OrgCompare" (no org names)
- Orgs row shows Source/Target dropdowns populated with DEVRCA and UATR
- Swap button swaps the dropdown values
- Manage Orgs opens a modal with the org list and an Add form
- Adding a new org (any alias + name) appears in the list and dropdown
- Removing an org removes it from both
- Refreshing the page restores the last selected source/target

- [ ] **Step 8: Commit**

```bash
git add templates/ui.html
git commit -m "feat: add org selector UI with swap button and Manage Orgs modal"
```

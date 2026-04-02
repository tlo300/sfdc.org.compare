# Browser-Based Salesforce Login — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users authenticate a new Salesforce org directly from the Manage Orgs modal instead of running `sf org login web` in the terminal first.

**Architecture:** Two new Flask endpoints (`POST /api/orgs/login`, `GET /api/orgs/login/status/<job_id>`) back a background thread that runs `sf org login web`. The browser polls for completion every 2 seconds and shows a status strip in the modal. The existing `addOrg()` JS function is replaced by `loginAndAddOrg()`.

**Tech Stack:** Python threading + subprocess, Flask, vanilla JS (fetch + setInterval)

---

## File Map

| File | Change |
|---|---|
| `orgcompare/server.py` | Add `_LOGIN_JOBS` dict, `start_login()`, `login_status()`, `_run_login()`, new imports |
| `templates/ui.html` | Add instance dropdown + status strip to modal; replace `addOrg()` with `loginAndAddOrg()` |
| `tests/test_server.py` | Add tests for the two new endpoints and `_run_login` |

---

## Task 1: Server — write failing tests

**Files:**
- Modify: `tests/test_server.py`

- [ ] **Step 1: Add the failing tests to `tests/test_server.py`**

Append below the last test in the file:

```python
from unittest.mock import MagicMock
from orgcompare.server import _run_login, _LOGIN_JOBS


# ── POST /api/orgs/login ────────────────────────────────────────────────────

def test_post_login_missing_alias_returns_400(client):
    res = client.post(
        "/api/orgs/login",
        data=json.dumps({"name": "My Org", "instance_url": "https://test.salesforce.com"}),
        content_type="application/json",
    )
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_post_login_missing_name_returns_400(client):
    res = client.post(
        "/api/orgs/login",
        data=json.dumps({"alias": "DEV", "instance_url": "https://test.salesforce.com"}),
        content_type="application/json",
    )
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_post_login_invalid_instance_url_returns_400(client):
    res = client.post(
        "/api/orgs/login",
        data=json.dumps({"alias": "DEV", "name": "Dev", "instance_url": "https://evil.com"}),
        content_type="application/json",
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid instance_url"


def test_post_login_returns_job_id(client):
    with patch("orgcompare.server.threading.Thread") as mock_thread:
        mock_thread.return_value.start = lambda: None
        res = client.post(
            "/api/orgs/login",
            data=json.dumps({
                "alias": "DEV", "name": "Dev Sandbox",
                "instance_url": "https://test.salesforce.com",
            }),
            content_type="application/json",
        )
    assert res.status_code == 200
    data = res.get_json()
    assert "job_id" in data
    assert len(data["job_id"]) == 36  # UUID format


# ── GET /api/orgs/login/status/<job_id> ────────────────────────────────────

def test_login_status_unknown_job_returns_404(client):
    res = client.get("/api/orgs/login/status/nonexistent-id")
    assert res.status_code == 404
    assert "error" in res.get_json()


def test_login_status_returns_running(client):
    _LOGIN_JOBS["test-running"] = {"status": "running"}
    res = client.get("/api/orgs/login/status/test-running")
    assert res.status_code == 200
    assert res.get_json()["status"] == "running"
    del _LOGIN_JOBS["test-running"]


def test_login_status_returns_done(client):
    _LOGIN_JOBS["test-done"] = {"status": "done"}
    res = client.get("/api/orgs/login/status/test-done")
    assert res.status_code == 200
    assert res.get_json()["status"] == "done"
    del _LOGIN_JOBS["test-done"]


def test_login_status_returns_error(client):
    _LOGIN_JOBS["test-error"] = {"status": "error", "error": "Auth cancelled"}
    res = client.get("/api/orgs/login/status/test-error")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "error"
    assert data["error"] == "Auth cancelled"
    del _LOGIN_JOBS["test-error"]


# ── _run_login ──────────────────────────────────────────────────────────────

def test_run_login_success_sets_done(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "source_org: A\ntarget_org: B\nmetadata_types: []\ndata_objects: []\n"
    )
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch("orgcompare.server.subprocess.run", return_value=mock_result):
        _run_login("job-ok", "NEWORG", "New Org", "https://test.salesforce.com")
    assert _LOGIN_JOBS["job-ok"]["status"] == "done"
    del _LOGIN_JOBS["job-ok"]


def test_run_login_cli_failure_sets_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "source_org: A\ntarget_org: B\nmetadata_types: []\ndata_objects: []\n"
    )
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "Authentication failed"
    with patch("orgcompare.server.subprocess.run", return_value=mock_result):
        _run_login("job-fail", "NEWORG", "New Org", "https://test.salesforce.com")
    assert _LOGIN_JOBS["job-fail"]["status"] == "error"
    assert _LOGIN_JOBS["job-fail"]["error"] == "Authentication failed"
    del _LOGIN_JOBS["job-fail"]


def test_run_login_duplicate_alias_sets_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "source_org: A\ntarget_org: B\nmetadata_types: []\ndata_objects: []\n"
    )
    # Pre-populate orgs.yaml with the alias we'll try to add
    (tmp_path / "orgs.yaml").write_text(
        "orgs:\n- alias: NEWORG\n  name: Existing\nselection:\n  source: ''\n  target: ''\n"
    )
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch("orgcompare.server.subprocess.run", return_value=mock_result):
        _run_login("job-dup", "NEWORG", "New Org", "https://test.salesforce.com")
    assert _LOGIN_JOBS["job-dup"]["status"] == "error"
    assert "already exists" in _LOGIN_JOBS["job-dup"]["error"]
    del _LOGIN_JOBS["job-dup"]
```

- [ ] **Step 2: Run tests to verify they all fail**

```bash
cd c:/Users/twanv/SalesforceProjects/OrgCompare
.venv/Scripts/python -m pytest tests/test_server.py -k "login" -v
```

Expected: All new tests FAIL with `ImportError` or `404`/`400` assertion errors (endpoints don't exist yet).

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_server.py
git commit -m "test: add failing tests for browser SF login endpoints"
```

---

## Task 2: Server — implement the login endpoints

**Files:**
- Modify: `orgcompare/server.py`

- [ ] **Step 1: Add imports at the top of `server.py`**

Replace the current import block:
```python
import yaml
from collections import defaultdict
from pathlib import Path
```

With:
```python
import subprocess
import sys
import threading
import uuid
import yaml
from collections import defaultdict
from pathlib import Path
```

- [ ] **Step 2: Add `_LOGIN_JOBS` dict after the `ORGS_FILE` constant**

After line `ORGS_FILE = "orgs.yaml"` add:
```python
_LOGIN_JOBS: dict = {}  # job_id -> {"status": str} or {"status": str, "error": str}
```

- [ ] **Step 3: Add `_run_login` helper function**

Add this function after the `_build_summary` function (before the first `@app.route`):
```python
def _run_login(job_id: str, alias: str, name: str, instance_url: str) -> None:
    """Run `sf org login web` in a background thread and update _LOGIN_JOBS."""
    sf = "sf.cmd" if sys.platform == "win32" else "sf"
    result = subprocess.run(
        [sf, "org", "login", "web", "--alias", alias, "--instance-url", instance_url],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        try:
            add_org(ORGS_FILE, alias, name)
            _LOGIN_JOBS[job_id] = {"status": "done"}
        except ValueError as e:
            _LOGIN_JOBS[job_id] = {"status": "error", "error": str(e)}
    else:
        _LOGIN_JOBS[job_id] = {
            "status": "error",
            "error": result.stderr.strip() or "Login failed",
        }
```

- [ ] **Step 4: Add the two new Flask endpoints**

Add these two routes after the `delete_org` route (after line `return jsonify({"status": "ok"})`):

```python
@app.route("/api/orgs/login", methods=["POST"])
def start_login():
    body = request.get_json(silent=True) or {}
    alias = (body.get("alias") or "").strip()
    name = (body.get("name") or "").strip()
    instance_url = body.get("instance_url", "https://test.salesforce.com")
    if not alias or not name:
        return jsonify({"error": "alias and name are required"}), 400
    if instance_url not in ("https://login.salesforce.com", "https://test.salesforce.com"):
        return jsonify({"error": "invalid instance_url"}), 400
    job_id = str(uuid.uuid4())
    _LOGIN_JOBS[job_id] = {"status": "running"}
    threading.Thread(
        target=_run_login, args=(job_id, alias, name, instance_url), daemon=True
    ).start()
    return jsonify({"job_id": job_id})


@app.route("/api/orgs/login/status/<job_id>")
def login_status(job_id: str):
    job = _LOGIN_JOBS.get(job_id)
    if not job:
        return jsonify({"error": "unknown job"}), 404
    return jsonify(job)
```

- [ ] **Step 5: Run the login tests and confirm they all pass**

```bash
.venv/Scripts/python -m pytest tests/test_server.py -k "login" -v
```

Expected output: all 11 login tests PASS.

- [ ] **Step 6: Run the full test suite to confirm no regressions**

```bash
.venv/Scripts/python -m pytest tests/ -v
```

Expected: 95 existing tests + 11 new = 106 tests, all PASS.

- [ ] **Step 7: Commit**

```bash
git add orgcompare/server.py
git commit -m "feat: add browser-based SF org login endpoints"
```

---

## Task 3: UI — update the Manage Orgs modal

**Files:**
- Modify: `templates/ui.html`

- [ ] **Step 1: Replace the Add form HTML in the modal**

Find this block (around line 281):
```html
      <div style="display:flex; gap:8px; align-items:center; margin-bottom:16px; flex-wrap:wrap;">
        <input id="new-org-alias" type="text" placeholder="Alias (e.g. DEVRCA)" style="padding:5px 8px; border:1px solid #ccc; border-radius:4px; font-size:14px; width:140px;">
        <input id="new-org-name" type="text" placeholder="Friendly name" style="padding:5px 8px; border:1px solid #ccc; border-radius:4px; font-size:14px; flex:1; min-width:140px;">
        <button class="btn-primary" onclick="addOrg()">Add</button>
      </div>
```

Replace it with:
```html
      <div style="display:flex; gap:8px; align-items:center; margin-bottom:8px; flex-wrap:wrap;">
        <input id="new-org-alias" type="text" placeholder="Alias (e.g. DEVRCA)" style="padding:5px 8px; border:1px solid #ccc; border-radius:4px; font-size:14px; width:130px;">
        <input id="new-org-name" type="text" placeholder="Friendly name" style="padding:5px 8px; border:1px solid #ccc; border-radius:4px; font-size:14px; flex:1; min-width:120px;">
        <select id="new-org-instance" style="padding:5px 8px; border:1px solid #ccc; border-radius:4px; font-size:14px;">
          <option value="https://test.salesforce.com">Sandbox</option>
          <option value="https://login.salesforce.com">Production</option>
        </select>
        <button class="btn-success" id="login-add-btn" onclick="loginAndAddOrg()">Login &amp; Add</button>
      </div>
      <div id="login-status" style="display:none; padding:8px 12px; border-radius:4px; font-size:13px; margin-bottom:8px;"></div>
```

- [ ] **Step 2: Replace the `addOrg()` JS function with `loginAndAddOrg()`**

Find this entire function (around line 416):
```javascript
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
```

Replace it with:
```javascript
    async function loginAndAddOrg() {
      const alias = document.getElementById('new-org-alias').value.trim();
      const name = document.getElementById('new-org-name').value.trim();
      const instanceUrl = document.getElementById('new-org-instance').value;
      const statusEl = document.getElementById('login-status');
      const btn = document.getElementById('login-add-btn');
      if (!alias || !name) {
        _setLoginStatus('Alias and name are required.', 'error');
        return;
      }
      // Disable form while login is in progress
      btn.disabled = true;
      document.getElementById('new-org-alias').disabled = true;
      document.getElementById('new-org-name').disabled = true;
      document.getElementById('new-org-instance').disabled = true;
      _setLoginStatus('\u23f3 Waiting for Salesforce login\u2026 (a browser tab should have opened)', 'info');
      let jobId;
      try {
        const res = await fetch('/api/orgs/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ alias, name, instance_url: instanceUrl }),
        });
        const data = await res.json();
        if (!res.ok) {
          _setLoginStatus(`Error: ${data.error}`, 'error');
          _enableLoginForm();
          return;
        }
        jobId = data.job_id;
      } catch (e) {
        _setLoginStatus('Network error. Is the server running?', 'error');
        _enableLoginForm();
        return;
      }
      // Poll for completion
      const poll = setInterval(async () => {
        let statusData;
        try {
          const r = await fetch(`/api/orgs/login/status/${jobId}`);
          if (r.status === 404) {
            clearInterval(poll);
            _setLoginStatus('Login session expired, please try again.', 'error');
            _enableLoginForm();
            return;
          }
          statusData = await r.json();
        } catch (e) {
          return; // network blip — keep polling
        }
        if (statusData.status === 'done') {
          clearInterval(poll);
          statusEl.style.display = 'none';
          document.getElementById('new-org-alias').value = '';
          document.getElementById('new-org-name').value = '';
          _enableLoginForm();
          await loadOrgsIntoDropdowns();
          _renderOrgsList();
        } else if (statusData.status === 'error') {
          clearInterval(poll);
          _setLoginStatus(`Error: ${statusData.error}`, 'error');
          _enableLoginForm();
        }
      }, 2000);
    }

    function _setLoginStatus(msg, type) {
      const el = document.getElementById('login-status');
      el.textContent = msg;
      el.style.display = 'block';
      if (type === 'info') {
        el.style.background = '#eaf4fd';
        el.style.border = '1px solid #2980b9';
        el.style.color = '#2980b9';
      } else {
        el.style.background = '#fdf0ed';
        el.style.border = '1px solid #e74c3c';
        el.style.color = '#e74c3c';
      }
    }

    function _enableLoginForm() {
      document.getElementById('login-add-btn').disabled = false;
      document.getElementById('new-org-alias').disabled = false;
      document.getElementById('new-org-name').disabled = false;
      document.getElementById('new-org-instance').disabled = false;
    }
```

- [ ] **Step 3: Manual smoke test**

```bash
.venv/Scripts/python main.py serve
```

1. Open http://localhost:5000
2. Click **Manage Orgs**
3. Enter an alias and friendly name, leave instance as **Sandbox**, click **Login & Add**
4. Verify a Salesforce login tab opens in the browser
5. Complete login — the modal should refresh and show the new org in the table
6. Verify the new org appears in the Source/Target dropdowns after closing the modal

- [ ] **Step 4: Commit**

```bash
git add templates/ui.html
git commit -m "feat: add browser-based SF login to Manage Orgs modal"
```

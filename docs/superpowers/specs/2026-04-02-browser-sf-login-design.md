# Browser-Based Salesforce Login — Design Spec

**Date:** 2026-04-02

## Problem

Adding an org to OrgCompare currently requires the user to run `sf org login web --alias X` in the terminal before the alias can be registered. This is a friction point: the user must context-switch to the CLI, remember the correct command, and only then use the Manage Orgs modal.

## Goal

Allow users to authenticate a new Salesforce org directly from the Manage Orgs modal, without touching the terminal.

---

## User Flow

1. Open **Manage Orgs** modal
2. Fill in:
   - **Alias** (e.g. `UATR`) — passed directly to `sf org login web --alias`
   - **Friendly name** (e.g. `UAT Release Sandbox`)
   - **Instance** dropdown: `Sandbox` (test.salesforce.com) or `Production` (login.salesforce.com) — defaults to Sandbox
3. Click **Login & Add**
4. The server starts `sf org login web` in a background thread; a browser tab opens to the Salesforce login page
5. A blue info strip appears in the modal: *"Waiting for Salesforce login… (a browser tab should have opened)"*. The form is disabled.
6. The browser polls every 2 seconds for job completion
7. On success: strip disappears, new org appears in the table, form re-enables
8. On error: strip turns red showing the error message, form re-enables for retry

---

## Architecture

### New Flask endpoints (`server.py`)

```
POST /api/orgs/login
  Body: {alias, name, instance_url}
  Returns: {job_id}  — immediately (non-blocking)

GET /api/orgs/login/status/<job_id>
  Returns: {status}            where status = "running" | "done" | "error"
        or {status, error}     on failure
```

A module-level dict `_LOGIN_JOBS: dict[str, dict]` tracks job state. No persistence — jobs are in-memory only.

### Background thread (`_run_login`)

Runs in a `threading.Thread(daemon=True)`:

```python
def _run_login(job_id, alias, name, instance_url):
    sf = "sf.cmd" if sys.platform == "win32" else "sf"
    result = subprocess.run(
        [sf, "org", "login", "web", "--alias", alias, "--instance-url", instance_url],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        try:
            add_org(ORGS_FILE, alias, name)
            _LOGIN_JOBS[job_id] = {"status": "done"}
        except ValueError as e:
            _LOGIN_JOBS[job_id] = {"status": "error", "error": str(e)}
    else:
        _LOGIN_JOBS[job_id] = {"status": "error", "error": result.stderr.strip() or "Login failed"}
```

`instance_url` is validated server-side to one of two allowed values before the thread starts.

### No changes to `orgs.py`

`add_org()` is called by the background thread after successful authentication — no new functions needed.

---

## UI Changes (`templates/ui.html`)

### Manage Orgs modal — Add form

**Before:**
```
[Alias input] [Name input] [Add button]
```

**After:**
```
[Alias input] [Name input] [Sandbox/Production dropdown] [Login & Add button]
[Status strip — hidden by default]
```

- Instance dropdown defaults to **Sandbox**
- "Add" button replaced by "Login & Add" 
- Status strip (`#login-status`) is hidden normally; shown as blue (waiting) or red (error)
- The existing `addOrg()` JS function is removed and replaced by `loginAndAddOrg()`

### `loginAndAddOrg()` JS function

1. Validate alias + name are non-empty
2. POST `/api/orgs/login` with `{alias, name, instance_url}`
3. Show blue waiting strip, disable form inputs and button
4. Poll `GET /api/orgs/login/status/{job_id}` every 2s
5. On `"done"`: hide strip, call `_renderOrgsList()`, re-enable form, clear inputs
6. On `"error"`: show red strip with error message, re-enable form
7. If poll returns 404 (job not found): show *"Login session expired, please try again"*

---

## Error Cases

| Situation | Behaviour |
|---|---|
| Alias already registered in orgs.yaml | `add_org()` raises `ValueError` → red strip: "Org 'X' already exists" |
| User cancels Salesforce login in browser | SF CLI exits non-zero → red strip with CLI stderr |
| SF CLI not found or crashes | Same — non-zero exit, stderr in strip |
| Server restarted mid-poll (job_id lost) | 404 → JS shows "Login session expired, please try again" |
| Modal closed while login in progress | Thread continues; org appears in list on next modal open if login succeeded |

---

## Testing

- Unit test `_run_login` with mocked `subprocess.run` (exit 0 and non-0)
- Unit test that `add_org` is called with correct args on success
- Unit test that `ValueError` from `add_org` maps to `"error"` job status
- Flask endpoint tests: POST `/api/orgs/login`, GET status (running → done, running → error, unknown ID → 404)
- Manual smoke test: login to a real sandbox, verify org appears in modal and dropdowns

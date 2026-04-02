# Console View — Design Spec

**Date:** 2026-04-02  
**Status:** Approved

## Overview

Add a real-time console panel to the right side of the OrgCompare UI that streams log output as Discover and Compare operations run. The panel helps users see exactly what the application is doing and identify inefficiencies (e.g., which object types take longest, how many records are fetched).

## Layout

The current single-column layout is split into two columns:

- **Left column (~65%):** existing top panel, status message (removed — replaced by console), tabs (Metadata/Data)
- **Right column (~35%):** new Console panel, always visible

On narrow viewports (< 900px) the console stacks below the main content.

The existing `#status` div ("Running compare — this may take a minute...") is removed. The console replaces it as the primary progress indicator.

### Console Panel Structure

```
┌─────────────────────────────────────────┐
│ Console         [Normal ▾]  [Clear]      │
├─────────────────────────────────────────┤
│ > Starting discover...                  │
│ > Querying metadata types...            │
│   Checking ApexClass (3 components)     │  ← grey (debug)
│ > Retrieved 47 metadata types           │
│ > Querying data objects (page 1)...     │
│ > Done — 312 types, 847 objects found   │  ← green (quiet/milestone)
└─────────────────────────────────────────┘
```

Dark background, monospace font, auto-scrolls to bottom. Fixed height with overflow-y scroll.

## Backend: SSE Streaming Endpoints

Two new streaming endpoints are added. The existing POST endpoints remain unchanged.

### `GET /api/discover/stream`

Streams discovery progress via Server-Sent Events. Each event is a JSON object:

```
data: {"level": "normal", "msg": "Querying metadata types..."}\n\n
data: {"level": "debug", "msg": "sf org list metadata-types --target-org DEVRCA --json"}\n\n
data: {"level": "quiet", "msg": "Done — 312 metadata types, 847 objects found", "done": true, "metadata_types": [...], "data_objects": [...]}\n\n
```

The final event has `"done": true` and carries the result payload. On error:

```
data: {"level": "error", "msg": "sf CLI failed: ..."}\n\n
```

### `GET /api/compare/stream`

Streams compare (retrieve + compare) progress. Request body parameters (`metadata_types`, `data_objects`) are passed as query string JSON to accommodate GET + EventSource.

Final event:

```
data: {"level": "quiet", "msg": "Done — 849 differences found", "done": true, "total": 849}\n\n
```

### Emit Callback Pattern

Each pipeline function gains an optional `emit` parameter:

```python
def run_discovery(org_alias: str, cache_path: str, emit=None) -> dict:
    ...

def retrieve_metadata(org_alias: str, metadata_types: list, output_dir: str, emit=None) -> None:
    ...

def retrieve_data(org_alias: str, data_objects: list, output_dir: str, emit=None) -> None:
    ...

def compare_metadata(..., emit=None) -> list:
    ...

def compare_data(..., emit=None) -> list:
    ...
```

`emit(level, msg)` is called inline at key steps. If `emit` is `None` (default), functions behave exactly as before — no behaviour change for existing callers or tests.

### Log Levels

| Level | When used |
|-------|-----------|
| `quiet` | Operation start/done milestones only (e.g., "Starting compare...", "Done — 849 diffs") |
| `normal` | Steps + counts (e.g., "Retrieving ApexClass from DEVRCA", "Queried Product2 — 412 records") |
| `debug` | sf CLI commands being run, raw record counts per pagination page, wall-clock timing per step |

The server always emits all levels. Filtering is client-side only.

## Frontend

### Verbosity Dropdown

Values: `Debug`, `Normal` (default), `Quiet`. Persisted to `localStorage` key `orgcompare_console_verbosity`. On change, CSS classes on existing log lines are toggled immediately — no new request needed.

Each log line rendered in the DOM carries a `data-level` attribute (`debug`, `normal`, `quiet`, `error`). A CSS rule hides lines below the selected threshold.

### Operation Flow

1. User clicks "Discover source org" or "Run Compare"
2. Console clears, `"Starting..."` line appended immediately
3. `EventSource` opened on the relevant stream endpoint
4. On each `message` event: parse JSON, append line with appropriate CSS class
5. Auto-scroll to bottom after each append
6. On `done` event: close `EventSource`, fire the existing results-loading logic (`loadResults()` for compare, discovery cache update for discover)
7. On `error` event: append red error line, close `EventSource`, re-enable buttons

### Color Coding

| Level | Color |
|-------|-------|
| `quiet` | Green (`#27ae60`) |
| `normal` | White/light grey (`#ddd`) |
| `debug` | Dim grey (`#777`) |
| `error` | Red (`#e74c3c`) |

### Backward Compatibility

The existing `POST /api/run-compare` and `POST /api/discover` endpoints remain. The UI switches to the new stream endpoints; the old ones still work for any scripts or external callers.

## What Gets Logged (Normal Level)

**Discover:**
- "Starting discovery on {org}..."
- "Listing all metadata types..."
- "Checking {N} metadata types for content (parallel)..." 
- "Found {N} metadata types with content"
- "Querying queryable data objects (page {N})..."
- "Found {N} queryable objects"
- "Done — {M} metadata types, {N} objects"

**Compare (retrieve + compare):**
- "Retrieving metadata from {source}... ({N} types)"
- "Retrieving metadata from {target}... ({N} types)"
- "Retrieving data from {source}... ({N} objects)"
- "  {ObjectName}: {N} records" (per object, at normal level)
- "Retrieving data from {target}..."
- "  {ObjectName}: {N} records"
- "Comparing metadata..."
- "Comparing data..."
- "Done — {N} differences found"

**Debug additions:**
- Full sf CLI command strings before each subprocess call
- Per-page record counts during pagination
- Wall-clock time per major step (e.g., "  took 4.2s")

## Files Changed

- `orgcompare/discover.py` — add `emit` param to `run_discovery`, `discover_metadata_types`, `_list_all_metadata_types`, `_type_has_content`, `discover_data_objects`
- `orgcompare/retrieve.py` — add `emit` param to `retrieve_metadata`, `retrieve_data`
- `orgcompare/compare.py` — add `emit` param to `compare_metadata`, `compare_data`
- `orgcompare/server.py` — add `/api/discover/stream` and `/api/compare/stream` SSE endpoints
- `templates/ui.html` — two-column layout, console panel, verbosity dropdown, EventSource wiring, remove `#status` div

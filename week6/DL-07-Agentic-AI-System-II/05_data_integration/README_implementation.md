# Module 05 foundation (provisional)

These three files are new files for `DL-07-Agentic-AI-System-II/05_data_integration/` on branch `supawit-05-data_integration`. They do not alter Modules 03 or 06. This implementation uses only the Python standard library and has no network or provider calls.

## What is implemented

1. Validate provisional canonical records and timed route segments. All datetimes must have a timezone offset. Route segments must cover the entire LineString in order.
2. Keep `observed_at`, `valid_at`, `issued_at`, `event_time`, `fetched_at`, and `expires_at` separate. A future forecast can have `valid_at` without `observed_at`.
3. Preserve source, lineage, severity, values, and quality flags without calculating or inventing a risk score.
4. Match fresh evidence to a route segment only when its source time overlaps that segment's ETA window and its point or line is within the configured corridor distance. A successful match reports that evidence category as `covered`; complete route coverage still requires every category on every segment to be `covered`.
5. Return `missing`, `stale`, or `unavailable` for other category/segment pairs and mark the context `degraded`. A segment with a mix of covered and non-covered categories also adds the aggregate `partial` quality flag. Unavailable provider records have no fabricated value.

## Run

From this directory:

```powershell
python -m unittest -v test_integration.py
```

Import `build_context` from `integration.py`. Its input is a dictionary with `run_id` and one or more `routes`, each containing a GeoJSON LineString and ordered `segments` with `start_index`, `end_index`, `enter_at`, and `exit_at`. Records use `canonical-record-v0.1-proposed` and require `record_id`, `record_kind`, `status`, `source.name`, and `fetched_at`; available records also need a value and source lineage. `expires_at` controls freshness. The test file contains complete synthetic examples.

## Pending team decisions

- Who produces candidate route geometry and per-segment ETA (03, 06, or routing service)?
- Final names, types, units, version, and category requirements for `IntegratedTravelContext` accepted by 06.
- How 03's mock-oriented `Record` and `IntegratedContext` will be replaced or adapted without misusing `observed_at` for forecasts.
- Provider semantics for polygons, transport delay/status, closures, and official alert severity. These are preserved as evidence; Module 05 reports coverage per category and segment, while Module 06 decides whether the whole route has complete coverage.

`integrated-travel-v0.1-proposed` is not a frozen interface. The output intentionally has `risk_score: null`; Module 06 owns risk evaluation.

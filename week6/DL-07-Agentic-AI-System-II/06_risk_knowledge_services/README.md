# Module 06 - Risk and Knowledge Services

This module owns three safety-evidence capabilities:

1. Explainable route-risk assessment.
2. Retrieval of approved and current disaster guidance.
3. Candidate-route exposure analysis with hard closure constraints.

It does **not** collect provider data (Module 04), normalize multi-source data
(Module 05), choose the final travel action, or generate the user-facing explanation
(Module 07).

## Current status

This is a tested foundation for the provisional cross-module contracts currently in
the repository. It accepts:

- Module 05's detailed `integrated-travel-v0.1-proposed` context; and
- Module 03's smaller draft `IntegratedContext` while its mocks are being replaced.

Outputs are strict and validate against Module 03's current `RiskResult`,
`KnowledgeResult`, and `RouteResult` schemas. No source file outside this module is
imported at runtime or modified.

## Implemented behavior

### Risk

- Validates the feature-schema version.
- Uses an auditable deterministic baseline for weather, disaster, transport, and
  official-restriction records.
- Treats an active official closure/restriction as a hard `HIGH` override.
- Returns level, normalized score, ordinal confidence, reason factors, model version,
  and derived-result provenance.
- Uses a conservative `HIGH`/low-confidence result when the integrated context is
  unavailable.
- Uses a conservative `MEDIUM` result with an unknown score and low confidence when
  only summary context is present, because `active_restriction=false` is not proof
  that weather, transport, and disaster evidence are complete.
- Treats `partial`, `freshness_unknown`, and provider `uncertain` flags from Module 05
  as data-quality issues.
- Contract tests exercise Module 05's matched TomTom transport and GDACS disaster
  records and verify that unmatched evidence is not scored.

The baseline score is **not a calibrated probability**. A trained model must pass the
documented time/location split, calibration, safety review, and registry process
before replacing `rule-baseline-v0.1.2`.

### Disaster knowledge retrieval

- Requires an active alert before retrieving guidance.
- Filters passages by approval, effective/expiry time, language, geography, and
  hazard type.
- Uses BM25-style lexical retrieval plus deterministic hazard/authority reranking.
- Returns authority, HTTPS source, document ID, page, section, validity, and score.
- Returns an empty evidence list when sufficiently grounded guidance is unavailable;
  it never fabricates emergency instructions.

No operational safety corpus is bundled. Approved documents must be reviewed and
supplied by the team before deployment. A multilingual embedding/vector backend can
later replace the text scorer without bypassing the metadata filters.

### Routes

- Calculates route distance from GeoJSON `LineString` coordinates.
- Calculates duration from timed route segments.
- Scores evidence matched to each route.
- Treats official closures and `AVOID` instructions as hard constraints.
- Identifies a clearly safer usable alternative only when essential coverage statuses
  (`current_weather`, `weather_forecast`, `transport_status`, `disaster_event`) for
  that route are `covered`, aligned with Contract Register Issue #2 (allowing `closure`
  and `official_alert` to remain optional when no live providers publish them).
- Does not claim a safe route when route context is unavailable.
- Does not currently infer `safer_later`; that requires an agreed hazard-validity
  interval contract.

## Package layout

```text
risk_knowledge/
  models.py       Input and output contracts
  risk.py         Risk baseline and safety overrides
  knowledge.py    Filtered disaster guidance retrieval
  routing.py      Route exposure and closure analysis
  evidence.py     Derived-result provenance
  service.py      Async facade for an adapter or future HTTP layer
tests/
  test_services.py
```

## Run tests

From this directory:

```powershell
python -m unittest discover -s tests -v
```

The suite also validates Module 06 outputs against Module 03's current draft schema.

## Pending cross-team decisions

- Freeze the detailed `IntegratedTravelContext` field names and feature version.
- Decide which service owns candidate route geometry and per-segment ETA.
- Define polygon intersection semantics in Module 05; point/LineString matching and
  disaster/transport time intervals are now implemented.
- Confirm confidence semantics across Modules 02, 03, 06, and 07.
- Approve risk thresholds, authoritative disaster documents, supported geography,
  and emergency-contact ownership.
- Add calibrated ML inference, vector embeddings, shared persistence, monitoring, and
  an HTTP adapter only after the relevant contracts are approved.

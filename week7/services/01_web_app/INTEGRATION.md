# Web integration handoff

## Scope

Work in this module only. Deploy owns the central Compose, active GitHub workflow and Dockerfile coordination under `docs/GIT_FLOW.md`. PR #16 is merged and branch commit `e0221c1` includes it. See [central Compose](../../docker-compose.yml), [Deploy guide](../../deploy/README.md) and [01-web workflow](../../.github/workflows/web-01.yml).

## CI entry point

Use Node 22 and pnpm 11.25.0, working directory `services/01_web_app`:

```text
pnpm install --frozen-lockfile
pnpm check
```

`check` runs component/unit tests, the integration-runner tests, typecheck, format check and production build. Runner tests use synthetic responses and do not prove live AI quality. The active `01-web` workflow runs for changes to this module on PRs targeting develop/main and on pushes to develop/main; manual dispatch is also available. [Run 36254446367](https://github.com/sakda1306/Advanced-Topic-in-Computer-Software-Course-Team-D-II/actions/runs/36254446367) passed on `e0221c1`. Recheck the latest commit after any new push. No service credentials are needed for this check. The production build is also exercised by the existing web Dockerfile.

Windows builds use normal Next output for `pnpm start`, avoiding privileged symlink creation during pnpm standalone tracing. Linux CI and Docker retain standalone output. Use a Linux runner for the deployment build.

## Central deployment prerequisites

- Build with `NEXT_PUBLIC_DEMO_MODE=false`; this is a build argument, not a runtime switch.
- Set `API_INTERNAL_URL` to API 02 on the internal network. Only API 02 is called by the web.
- Configure real 03/04/05/06/07 endpoints on the backend and related services. Record their commit/image versions and verify their health/readiness before testing.
- Seed two distinct ordinary test users and a known football dataset, including fixtures and standings. Use an isolated test database.
- Start the web only after API is ready. `/health` on the web verifies the web process, not the health of the entire service chain.
- Keep module `docker-compose.yml` for the existing stub demonstration. It does not prove central integration.

## HTTP integration against a verified dataset

`pnpm test:integration` uses no stub control commands, no fixed demo credentials and no hardcoded football scores. It creates chat/history/feedback for two test users and logs out both users. It reads football data and checks that ordinary users cannot access admin stats. It does not ingest, publish reports, delete documents, change preferences or disable users.

Provide a local JSON array using facts checked against the test database. Example shape only; replace the question, document ID, expected facts and timestamp before running:

```json
[
  {
    "name": "Known football fact",
    "message": "REPLACE_WITH_A_QUESTION_ANSWERED_BY_THE_TEST_DATA",
    "expectedRoute": "football_rag",
    "expectedDocIds": ["REPLACE_WITH_VERIFIED_DOCUMENT_ID"],
    "expectedAnswerIncludes": ["REPLACE_WITH_VERIFIED_FACT"],
    "expectedDataAsOf": "2026-09-24T00:00:00+07:00",
    "expectedFallback": null
  },
  {
    "name": "Ambiguous question",
    "message": "REPLACE_WITH_AGREED_AMBIGUOUS_QUERY",
    "expectedRoute": "clarify",
    "expectedDocIds": [],
    "expectedAnswerIncludes": ["REPLACE_WITH_AGREED_CLARIFICATION_TEXT"],
    "expectedDataAsOf": null
  }
]
```

For no-data cases use the agreed route, an empty document list, the expected apology/no-data text and `expectedFallback: "retrieval_empty"`. For a controlled retrieval outage use `retrieval_down`. Include both grounded and source-free cases; use `expectedDataAsOf: null` for timeless trivia when appropriate. Expected document IDs are an exact set, while answer fragments allow natural-language variation. This is a deterministic acceptance test, not a general evaluator of factual accuracy.

Set these environment variables in the test session (passwords should come from local test secrets or CI secrets; do not commit them):

| Variable | Meaning |
| --- | --- |
| `WEB_URL` | Web origin; default `http://localhost:3000` |
| `INTEGRATION_CASES` | Path to the verified JSON case file |
| `INTEGRATION_USER_A`, `INTEGRATION_PASSWORD_A` | First ordinary test user |
| `INTEGRATION_USER_B`, `INTEGRATION_PASSWORD_B` | Second, distinct ordinary test user |

Then run `pnpm test:integration`. Missing configuration fails before network requests. The runner checks route, facts, exact source IDs, citation references, timestamps, request-ID correlation, persisted answers/sources, feedback, account isolation, football match identity and logout. It polls history for up to about five seconds for asynchronous persistence. It does not claim that services are real merely because HTTP checks passed: record and verify the deployment separately.

## Browser and full-system acceptance

Record browser, viewport, web commit and backend service versions. Test Login, Chat, Football and Admin at desktop and mobile widths with all five club themes. Verify readable errors, keyboard navigation, mascot position, citation focus and timestamps against the network response.

With an admin test account, verify pipeline transitions to an actual terminal status, report draft/edit/publish/unpublish, feedback/log correlation, quota and downstream failures. Run mutations only on the isolated dataset. Coordinate service outage/restart scenarios with Deploy. Check 401/403/409/429/502/504 and retrieval startup through the real API.

## Open dependencies

- Contract v1.3 adds optional `context.last_ingest_at` on API-to-Router requests, not on Web requests. Test fallback text with a known timestamp and with null/missing values after the supporting API/Router versions are integrated. The Web must not infer this value from `created_at` or substitute it for the independent response field `data_as_of`.

- API 02 currently maps `INDEX_NOT_READY` from 05 to `RETRIEVAL_UNAVAILABLE`; Web supports either response and does not interpret either as an empty database.
- API 02 has no Web endpoint for 05 rebuild-job polling. The KB page confirms acceptance and job ID only. Adding polling needs an agreed API contract; a vanished job after 05 restart is unknown completion, not success.
- History currently exposes content/sources/route/rating, without trace or `data_as_of`. Web does not reconstruct missing timestamps from message creation time.
- Strict database-only answers require a team decision: the current contract permits general knowledge and trivia fallback. Web displays the actual answer and its provenance; source presence alone does not prove that the answer is true.
- The existing stub sends a canned match answer for unrecognized input. Replacing the stub with the real chain and testing relevance/grounding remains required.
- Historical-data expansion remains Could until the main integration acceptance checks pass.

## PR #4 review handoff

The owner handoff assigns review/approval to Peem and merge to Sakda. Before review, attach the latest commit and successful `01-web` run, local `pnpm check`, Docker demo smoke and browser results. Run the module demo from `services/01_web_app`, then shut it down with `docker compose down` without deleting volumes. Report stub limitations explicitly. Real 03–07 integration remains a shared follow-up rather than a result implied by demo smoke. Prepare evidence locally until submission is authorized.

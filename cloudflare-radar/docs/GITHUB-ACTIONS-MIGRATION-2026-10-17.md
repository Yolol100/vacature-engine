# Vacature Radar - Cloudflare to GitHub Actions, phased migration
Date: 2026-10-17
Owner: vacature-search; process controller: webactueel-workflow
State: READ-ONLY IMPLEMENTATION, NOT PRODUCTION GO

## Verified initial state
- PR #120 and #121 merged into main. Current main at inventory: 39ed84e06aae9f23992eca84af1780cc9f65ee43.
- Cloudflare Worker vacature-radar binding RADAR_ENABLED=0 and RADAR_PIPELINE_MODE=off (live readback). Its existing one-minute Cron remains configured but cannot pass both activation gates.
- D1 database vacature-radar-state is retained. Live D1 query found exactly 26 baseline observations, 0 temporary micro:v2 observation rows, and 24 metadata rows.
- A five-column, identity-by-identity comparison of these 26 D1 observations with the Google Radar result spreadsheet Radar State tab showed 26 exact matches, 0 missing, 0 extra, 0 duplicate keys.
- Live Vacature Register Config radar_enabled=FALSE and radar_delivery=none. Vacature Register remains authoritative for source, vacancy and application state.
- The Google result spreadsheet Nieuwe vacatures and Runs tabs contained only headers at initial inspection.
- Existing independent Python ingestion workflows are retained unchanged. They are NOT this review-only Cloudflare successor.

## New proof-of-concept execution
- cloudflare-radar/src/actions-review.mjs reuses existing logic.mjs, official-ats.mjs and google-sheets.mjs.
- One bounded Node.js run reads source/employer statuses, vacancy history, application statuses and submission events, existing Radar results and Radar State baselines, and official ATS data for the original three source/employer pilot pairs.
- Official ATS observation and preliminary technical-interest filtering are NOT full authenticity, live remote-from-NL, current vacancy status, language, candidate-evidence or ranking proof. The only possible output is a queue for manual specialist review; it may not be labelled an approved vacancy.
- Every run is read-only: no Google Sheets updates, no D1 writes, no emails, no submissions, no persistence or new controller.
- Limit up to 10 manual review observations, stop duplicate identities and official job URLs, fail closed on history/headers and report partial source errors. Public run logs contain official public vacancy information only.
- Credentials are received through GitHub Actions secret GOOGLE_SERVICE_ACCOUNT_JSON if present. This has NOT been verified in the repository secret configuration, nor copied from Cloudflare.
- The existing 26-record Radar State mirror is historical dedupe input only. It is NOT a continuously synchronized checkpoint store. Runner ephemerality means fresh uncommitted candidates can be rediscovered across runs.
- GitHub workflow may be triggered by manual workflow_dispatch or owner-authored issue title exactly [radar] review 5 or [radar] review 10. Issue trigger only works once the workflow is present on the default branch. The connected GitHub ChatGPT app can create an issue but does not presently expose a workflow_dispatch API.
- GitHub workflow includes PR-only mocked regression checks; read-only job will not execute on pull_request. No schedule.

## Safe acceptance and continuation
1. Run CI against the migration PR. Inspect jobs/steps and actual failure evidence, not just green status.
2. Verify an Actions secret is configured and has access only to required Google Sheets. Never reveal token/key values.
3. After explicit merge and production-read-only permission, trigger a bounded single test and read official run logs, correlate input issue/run and inspect result correctness; verify both sheets and D1 unchanged.
4. Broaden from the existing three pilot ATS pairs only if live Config/source tier and official verified routes justify coverage. Apply all vacature-search gates before presenting any final role.
5. Design durable idempotent checkpoint/processed-result commits with readback, optimistic concurrency and crash recovery. The 26-row Radar State mirror is a candidate durable storage target, but atomic upsert semantics, history conflicts, and writing permissions are unproven. Keep D1 untouched/read-only until a tested migration plan and backup exist.
6. Test interrupted/restarted runs, simultaneous starts, retry handling, Google/API credential errors, source failures, historical application dedupe and negative assertions against unapproved Sheets writes/submissions. Independent QA accepts only live proof.
7. Preserve original Worker, D1 data, disabled settings, credentials and rollback until all gated acceptance evidence exists. No production activation or teardown without explicit approval.

GO/NO-GO: NO-GO for full migration, durable writes, Cloudflare retirement or production activation. This PR is a safe read-only precursor only.

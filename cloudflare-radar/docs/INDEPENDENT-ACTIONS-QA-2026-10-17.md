# Independent acceptance audit: GitHub Actions Vacature Radar
Date: 2026-10-17
Repository: Yolol100/vacature-engine
Change set: draft PR #134, based on main 39ed84e06aae9f23992eca84af1780cc9f65ee43
Controller: webactueel-workflow; vacancy owner: vacature-search
Disposition: NO-GO for production activation and Cloudflare retirement

## Evidence classes
- LIVE READBACK: current Cloudflare, D1, Google Sheets and GitHub repository metadata checked without mutations.
- CI INTEGRATION: code executed in official GitHub Actions with temporary local bare Git remotes and/or generated fake OAuth credentials. No live business-system write.
- MOCK/UNIT: fixture source, failure and duplicate tests run in CI. This never proves live API credentials or official vacancy eligibility.
- BLOCKED: exact production operation intentionally not performed without explicit authorization or required connector capability.

## Independent baseline readback
- Cloudflare GET Worker binding: RADAR_ENABLED=0, RADAR_PIPELINE_MODE=off. The original * * * * * Cron remains configured but is gated off. Do not treat this as physical removal of its scheduler.
- D1 live SELECT: exactly 26 observations, all status=baseline; zero micro:v2 metadata rows.
- Google result sheet Radar State A1:E40: exactly 26 data rows; full five-field tuple (identity, source_instance, URL, status, first_seen_at) exact match 26/26 with live D1; 0 missing, extra or duplicate keys.
- Google result tabs Nieuwe vacatures and Runs: exactly one header row, no data rows.
- Register live Config: radar_enabled=FALSE, radar_delivery=none, radar_state_branch=radar-state.
- Existing GitHub radar-state branch head c3043f7936d330b45d34f29a26b64a1e0702d333 contains its original five technical files (state.sqlite3, first-seen-queue.json, latest.json, radar-ack.json, source-health.json); new review-observations.json is NOT yet present.
- Draft PR not merged; main remains unchanged. No production workflow dispatch or live issue event was run.

## Required acceptance matrix
| # | Scenario | Current evidence | Disposition |
|---|---|---|---|
| 1 | Ordinary successful search | Deterministic official ATS fixture -> preliminary review only | MOCK PASS; LIVE NOT TESTED |
| 2 | No new roles | Empty official feed returns empty review_ready | MOCK PASS |
| 3 | Limit maximum 10 | 23 inputs -> at most 10 preliminary candidates | MOCK PASS |
| 4 | Invalid/inactive source/employer | Registry status checks reject before polling | MOCK PASS |
| 5 | Already-known vacancy | Live register identity logic suppresses known URL/ID | MOCK PASS |
| 6 | Previously submitted application | Applied status and exact URL suppress role | MOCK PASS |
| 7 | Missing vacancy ID, official URL available | Strong official URL suppresses submitted application | MOCK PASS |
| 8 | Google API failure | Mock Sheets HTTP 503 blocks ATS and all writes | MOCK PASS |
| 9 | Transient ATS failure | One bounded 5xx retry; 429 and long Retry-After fail closed | MOCK PASS |
| 10 | Expired or missing authentication | Missing secret and fake OAuth failure/rotation tested | PARTIAL; REAL TOKEN EXPIRE UNTESTED |
| 11 | Interrupted Actions run | Staged Git receipt and stale-branch CAS tested in temporary Git | CI INTEGRATION PASS; LIVE CANCELLATION UNTESTED |
| 12 | Restart after interruption | Same run ID detects completed receipt, skips OAuth and ATS; no-op Git replay | CI INTEGRATION PASS; LIVE UNTESTED |
| 13 | Two concurrent commands | Two read-only calls, branch-CAS conflict and queue:max contract | SIMULATED PASS; LIVE CONCURRENCY UNTESTED |
| 14 | Prevent duplicate results | Strong identity/URL and durable receipt de-duplication tests | MOCK/CI PASS |
| 15 | Preserve historical data | 26/26 D1->Sheet tuple readback, original Git state files unchanged | LIVE READBACK PASS |
| 16 | Never submit applications | Review-only output: submissions=0, no submission path or email action | STATIC/MOCK PASS; NO LIVE SUBMISSION TEST |
| 17 | No unwanted Google Sheets updates | OAuth spreadsheets.readonly; result sheet header-only after repo changes | STATIC + LIVE READBACK; END-TO-END STILL OPEN |
| 18 | Complete new ChatGPT-triggered execution | Owner issue transport designed, but default-branch merge and live credentials not proven | BLOCKED |

## Architecture and security results
- Reuses the original Cloudflare official ATS and dedupe logic without a second scanner.
- One consolidated .github/workflows/vacature-radar.yml. An older duplicate review Actions workflow is removed from the PR. The old first-seen *live writer job* was removed from the new unified workflow; its persisted data is retained.
- GitHub push/PR only runs tests; no schedule.
- Read-only review requires repository owner command or explicit workflow dispatch; no Sheets writes or application side effects.
- Technical receipts would be appended as a new file on the pre-existing radar-state branch only after owner manual persist_review=true AND repository variable RADAR_PERSIST_APPROVED=yes. This condition has NOT been enabled or verified.
- Git write job has a separate contents:write permission; the default review job is contents:read. Commit is non-force, exact base SHA checked before write, and remote readback is byte-matched.
- Replay after a successful but interrupted branch write is recognized by GitHub run ID and skips further network polling.
- Existing source code, D1, Worker, credentials and archival project data were not deleted.

## Release blockers / exact resumption
1. Inspect GitHub Actions secret metadata and verify the required GOOGLE_SERVICE_ACCOUNT_JSON is available to the permitted read-only job. Do not copy or expose key material.
2. Obtain specific permission to merge PR #134 and run a single restricted read-only end-to-end workflow. A draft PR + green CI is not that permission.
3. Once permitted, test owner-authored ChatGPT issue command, correlate run ID, GitHub actor, requested limit, network/API success, and validate actual result output. Verify D1 and Sheet unchanged immediately afterward.
4. Separately request approval to set RADAR_PERSIST_APPROVED=yes and perform one commit to radar-state, with preflight and readback. Never infer approval from the existence of an input.
5. Independently test real timeout/cancellation, repeat-run, concurrency and restore. Check no unintended workflow was fired on push, PR or issue.
6. Complete vacancy-search authenticity, location/fully-remote Netherlands eligibility, working/application language and evidence-grounded fit/score review before calling any vacancy verified.
7. Only after all gates, request distinct permission to retire the Cloudflare Cron/Worker, D1 and old secrets. Preserve the 26 source records and rollback until transferred/verified.

Resume at draft PR #134, updated branch migration/github-actions-review-only-20261017. Preserve existing radar-state branch and all 26 D1 records. 

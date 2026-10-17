# Webactueel Vacature Radar: Cloudflare to GitHub Actions

Status: **DRAFT PR #134; NO-GO for production activation or Cloudflare retirement.**
Controller: webactueel-workflow. Vacancy policy/QA owner: vacature-search.
Repository: Yolol100/vacature-engine.

## Evidence-based baseline (2026-10-17)
- PR #120 and PR #121 already merged on main before migration.
- Live Cloudflare Worker vacature-radar had RADAR_ENABLED=0 and RADAR_PIPELINE_MODE=off. The old Cron remained configured but was gated off.
- Live D1 database vacature-radar-state had 26 baseline observations and no temporary v2 observations. Never delete or reset its historical records.
- Radar result spreadsheet, tab Radar State, had 26 exact five-field matches with D1 (no missing/extra/duplicate identities) at the verified readback.
- Result tabs Nieuwe vacatures and Runs were header-only.
- Vacature Register remains authoritative. Its Config includes radar_enabled=FALSE, radar_delivery=none and radar_state_branch=radar-state. Application history lives in Vacatures, Applications and ApplicationEvents.
- GitHub already had a separate first-seen radar technical branch radar-state (SQLite, acknowledgements, queues and health). That branch is reused, not deleted or replaced.

## Consolidated workflow
One workflow: .github/workflows/vacature-radar.yml.

| Trigger | Allowed action |
| --- | --- |
| push / pull_request | Python ingestion/first-seen tests only; Cloudflare Node checks run through the existing CI file |
| workflow_dispatch (repository owner), persist_review=false | Read-only official-source technical review; no writes |
| exact owner issue title [radar] review 5 or [radar] review 10 | Same read-only technical review |
| workflow_dispatch (owner), persist_review=true AND repository variable RADAR_PERSIST_APPROVED=yes | Optional technical checkpoint on existing radar-state branch |
| schedule | **Not configured** |

The older first-seen live writer and separate duplicate .github/workflows/vacature-review-actions.yml workflow were removed from the *new workflow definition*. Existing ingestion code, historical radar-state branch and Cloudflare rollback code remain intact. The unrelated existing .github/workflows/vacature-ingestion.yml is unchanged.

Workflow concurrency queue:max serializes manual radar executions (up to GitHub's documented queue limit) without replacing pending requests. PR/push tests share a separate CI concurrency group. All third-party actions are pinned by SHA.

## Technical review
One bounded Node.js invocation reuses:
- cloudflare-radar/src/google-sheets.mjs (Actions uses only spreadsheets.readonly OAuth);
- cloudflare-radar/src/official-ats.mjs;
- cloudflare-radar/src/logic.mjs for strict ATS IDs, URLs, source/account checks, and known/applied identity reconciliation;
- read-only live Config/Bronnen/Vacatures/Applications/ApplicationEvents and Radar State/previous results;
- cloudflare-radar/src/actions-review.mjs / actions-review-cli.mjs.

Review fails closed when missing or invalid live policy flags, headers, baseline, auth, source/employer registration or history. Maximum 10 technical observations for manual review. It does NOT verify current publication/open status, scam/authenticity, remote/NL work eligibility, language, target family, candidate evidence or final score. Those remain vacature-search's live policy gates and must be completed before a job may be presented as an eligible verified match. No automatic applications, emails or registration status changes exist.

## Durable technical receipts (guarded and opt-in)
- Only the **existing** radar-state branch may contain a new file review-observations.json, schema_version=1. It contains public official ATS identity/URL/title, first-seen UTC and deterministic run digest. It is NOT a replacement for the Vacature Register.
- The initial state file is absent until a separately approved run; restore fails if the underlying branch is absent rather than creating a new database/branch.
- A valid checkpoint is built only from a complete status=review_ready, read-only receipt with zero errors, zero Sheets writes and zero submissions.
- Read source branch and exact base SHA before ATS work; re-fetch and require same base SHA before commit; git push is non-force and has exact readback comparison. A changed branch fails closed and requires a fresh run.
- GitHub Actions job token is contents:read by default. Only the separate, owner-only, double-gated checkpoint job gets contents:write.
- After an interrupted job is re-run with its same GitHub run ID, an already committed receipt is detected before OAuth and ATS calls, staging an identical no-op checkpoint. If interruption happened before commit, an explicit new run can safely repeat a read-only crawl.
- Partial source failure does not checkpoint. A conflicting same-run digest, duplicate identity, untrusted URL or exceeded history capacity causes a hard failure.
- An operator can inspect last durable technical observations via radar-state:review-observations.json, or view read-only run output in official GitHub Actions logs. GitHub state does not determine application status.
- The existing D1 baseline remains untouched and is independently checked against Radar State until a separately approved final retirement gate.

## Independent testing and status
- Regression tests mock Google and ATS failures, invalid providers, missing secrets, applied roles without IDs, prior shown vacancies, broken headers, 10-job cap, duplicate sources, concurrent read-only calls and replay.
- Native local-bare-Git integration tests verify actual branch checkpoint commit, exact readback, stale-SHA rejection, no-op repeat, owner/approval restrictions and historical file preservation.
- The new tests run through cloudflare-radar-ci.yml. Workflow PR tests have no secrets and must never launch live review jobs.
- Green CI is *not* proof of live service account access or a complete migration. Check the exact final commit, GitHub job logs and live Sheets/D1 readback again before any release claim.

## Remaining release gates (NO-GO)
1. Verify the current GitHub Actions service-account secret is present/authorized. Do not extract or duplicate private keys from Cloudflare; do not put keys/tokens in logs or code.
2. Obtain explicit permission to merge the default-branch workflow and perform a single bounded **read-only** end-to-end dispatch or ChatGPT issue command. Verify exact run ID and status, actual ATS/Google responses and public output.
3. Verify unchanged 26 D1 baselines, unchanged business register and no unintended Sheet/mailbox/application writes after that live run.
4. Separately approve any opt-in technical checkpoint activation. The RADAR_PERSIST_APPROVED repository variable is not configured or verified here. Do NOT set it automatically.
5. Exercise real interrupted/crash/race scenarios under the authorized runner and confirm branch CAS / readback, identity dedupe and recovery. Unit tests alone are insufficient.
6. Apply live vacature-search official-verification and candidate-evidence gates before claiming fully verified vacancies.
7. Receive explicit permission before Cloudflare shutdown/removal, D1 migration or secret cleanup. Keep rollback until proof.

## ChatGPT use after explicit default-branch activation
- "Start de Vacature Radar": create repository-owner issue [radar] review 5.
- "Zoek maximaal 10 nieuwe vacatures": create repository-owner issue [radar] review 10.
- "Laat de laatste resultaten zien": inspect correlated Actions run and the existing radar-state branch read-only.
- "Controleer gevonden vacatures": perform a new official-policy, authenticity, location and fit check under vacature-search; no auto-submit.
- "Hervat een onderbroken run": read the run ID/receipt; rerun safely only after live-state and approval checks.

Neither creating an issue nor the GitHub connector alone proves the job actually ran. Always correlate the issue, workflow run, exact head commit and results.

## Rollback
Leave draft PR #134 unmerged until acceptance. Revert only the merged workflow/source commits if later needed; do not delete D1, the 26 historical observations, Google sheets, existing radar-state branch or unrelated ingestion data. The optional technical receipt file is append-only and independent from application truth.

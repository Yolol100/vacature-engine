# Webactueel Vacature Radar — current GitHub Actions migration

Updated: 2026-10-17. This document replaces the outdated draft-PR status.

**Status: manual, read-only technical review LIVE and verified. Full migration and production persistence: NO-GO until separate approval and real recovery proof.**

## As-built architecture
- Repository: Yolol100/vacature-engine. Main commit at this verification: 32c8a5229cd248c28d9283b4bf8f48131105e397.
- PR #134 introduced the consolidated manual workflow; PR #143 expanded supported ATS scope; PR #145 temporarily quarantined two custom host mappings; PR #150 added Personio and Workable; PR #153 verified the two employer-owned Greenhouse URL contracts. All merged.
- One review workflow: .github/workflows/vacature-radar.yml. Owner-only manual dispatch or exact owner-authored issue [radar] review 5 / [radar] review 10. PR/push run tests only. No GitHub schedule.
- Node.js reviewer uses existing official-ats, logic and Google Sheets read-only APIs, plus ingestion/source-specs.radar.json as its only technical source manifest.
- Technical state remains on the original radar-state branch. The Vacature Register (Config, Bronnen, Vacatures, Applications, ApplicationEvents, CandidateEvidence) is authoritative for all business/application policy and history. Technical preview is not an eligible or verified vacancy.
- Eleven supported and live-checked employer/ATS pairs: Automattic/Greenhouse, Kinsta/Lever, SiteGround/Lever, Acquia/Greenhouse, GitLab/Greenhouse, DigitalOcean/Greenhouse, Pantheon/Greenhouse, Zapier/Ashby, Syde/Personio, Awesome Motive/Workable and Human Made/Workable. Both provider and employer must be active in the live Bronnen tab.
- DigitalOcean/digitalocean98 and Pantheon/pantheon are verified in the shared manifest only after official GET evidence proved 197/197 and 21/21 employer-owned URLs: www.digitalocean.com/careers/position/apply?gh_jid=ID and pantheon.io/about/careers/detail?gh_jid=ID. Only these exact HTTPS host/path/tenant/numeric-ID contracts are accepted.
- The three Personio/Workable entries reuse existing Python ingestion adapters through an Actions-only read-only bridge (PR #150). Workable's official tenant feed provides job identity; canonical links are employer-scoped and validated. All eleven configured source pairs now pass technical read-only transport; this is not proof of any qualified Netherlands-executable vacancy.
- The manual Node reader supports at most 1,000 records / 6 MB per selected official source. Cloudflare Worker retains its existing smaller caps.
- Manual requests are serialized with GitHub Actions queue:max. Review job token is read-only. Technical checkpoint job is separate, owner-only and requires both the persist_review dispatch input and repository variable RADAR_PERSIST_APPROVED=yes.

## Production evidence
- Earlier read-only workflow dispatch 39044976255: success, 3 pilot sources, 26 records already known, zero new observations.
- Owner issue test 39046735779: success, verified ChatGPT owner-trigger transport to Actions and two-Sheet OAuth reads.
- Initial expanded-source test 39047475406: partial, with 2 strict ATS host failures; no writes. PR #145 quarantined those mappings, without relaxing host validation.
- After PR #145, owner issue #146 (run 39047802494): success, status=review_ready, six sources, 270 ATS observations, 26 previously known, five preliminary review candidates, zero failures.
- Owner issue #147 (run 39047804812): success, status=review_ready, six sources, 270 observations, 26 previously known, ten preliminary review candidates, zero failures. The two issue-triggered runs were queued and processed separately.
- Owner issue #151 (run 39050720551; main dafd8f191bdb551c23bdfa991771d8124dbdce0c): success, status=review_ready, nine sources, 295 public ATS observations, 26 historical, ten preliminary candidates, zero provider failures, no Google Sheets, D1 or application writes. No Netherlands execution / fit decision.
- Owner issue #154 (run 39053605076; main 9c69f9a4d03f34752e70298b04cb757ce0eeed1f): success, status=review_ready, eleven active official ATS pairs, 513 observations, 26 historical, ten preliminary review items, zero source failures, zero Sheets/D1/application writes. The preview contains location-limited roles; do not promote these to NL-eligible matches without specialist verification.
- For these live runs: application_submissions=0, google_sheet_rows_written=0 and manual_review_required=true. No vacancy has been promoted to a fully verified, Netherlands-eligible match by the technical reviewer.
- **Separate ingestion side-effect:** changing `ingestion/source-specs.radar.json` on main also triggered the unrelated existing `.github/workflows/vacature-ingestion.yml` push writer. [Run 39047791175](https://github.com/Yolol100/vacature-engine/actions/runs/39047791175) failed at its **first write**, Google Sheets `Bronnen!G:L` values:batchUpdate, with HTTP 403; subsequent Runs append and technical checkpoint were not executed. Its integration state branch `ingestion-state` is unchanged at `489b7f53e2534088d91621dd8312ab1ce1b3c163`. This is not a Radar review write. Avoid touching the shared radar source manifest casually; future ingestion side-effects require separate review. No successful Google business write was observed from this failed run.
- PRs #143, #145, #150 and #153 passed CI, workflow regression, Cloudflare and relevant ingestion checks. PR #153 additionally proves strict custom employer URL host and job-ID matching.

## Independent state readback after the two successful issue runs
- Cloudflare D1: 26 baseline identities, all unique; the exact five-field tuples match the 26 rows in Google result spreadsheet Radar State (26/26).
- Google result tabs Nieuwe vacatures and Runs: header only; no new rows. Vacature Register Config continues with radar_enabled=FALSE, radar_delivery=none, radar_state_branch=radar-state.
- Existing radar-state branch head: c3043f7936d330b45d34f29a26b64a1e0702d333. Original files preserved: state.sqlite3, first-seen-queue.json, latest.json, radar-ack.json, source-health.json.
- review-observations.json is still absent: no live production checkpoint was attempted or approved.
- Cloudflare Worker settings: RADAR_ENABLED=0, RADAR_PIPELINE_MODE=off. Historic Cloudflare Cron (* * * * *) and D1 are retained intact for rollback. Do not confuse disabled execution with removed infrastructure.
- The unrelated GitHub ingestion-state branch remained unchanged after an unwanted ingestion push trigger. Google Sheets write attempt returned 403 before the first batch update completed. No accepted register update or new run row from that attempt is evidenced.

## Open release gates
1. Obtain separate, explicit authorization before setting RADAR_PERSIST_APPROVED=yes and performing any real technical checkpoint write. A broad task request is not this specific production approval.
2. Prove durable write/readback, repeated run idempotence, interruption/replay and branch compare-and-swap with real GitHub runner state. Existing isolated bare-Git and mock tests do not prove a real production restart.
3. Verify current official role, fully remote/NL eligibility, NL/EN language, authenticity, CandidateEvidence, fit and score independently before calling any preliminary observation a qualified vacancy. Never auto-apply or email.
4. Preserve Cloudflare Worker, Cron, D1 and rollback until separate explicit retirement authorization after full migration proof. Do not enable automatic scheduling.

## Safe resumption
Read current main and latest runs; verify the live register and D1/Sheet baseline. Continue with a narrowly approved checkpoint run, compare its exact state readback, then run genuine crash/replay and concurrency tests. Leave all application and Google Sheets business data read-only. Do not claim COMPLETE while any above gate is open.

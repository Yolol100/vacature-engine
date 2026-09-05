# Vacature Ingestion

Policy-free bulk ingestion component for the Webactueel vacature system. It converts public ATS/API/JobPosting data into `JobObservation 1.1` compatible observations and owns only technical ingest state.

## Boundaries

This component does **not** own candidate fit, WordPress relevance, salary/language/remote policy, application state, scoring or outreach. Those remain with `vacature-search`, the live Vacature Register and the deterministic `vacature_engine` package.

## Adapters

Fast/targeted public sources:
- Greenhouse public Job Board API
- Lever public Postings API
- Ashby public Job Postings API
- SmartRecruiters public postings API
- Generic public HTML pages exposing Schema.org `JobPosting` JSON-LD

Daily secondary discovery feeds:
- Himalayas public JSON API with cursor pagination
- Jobicy public Remote Jobs API
- Remotive public API (24h-delayed; attribution metadata retained)

Secondary feeds remain discovery evidence. `vacature-search` must verify a promising role on the canonical employer/ATS page before eligibility and ranking.

## Review queue

Every `ingest-many` output contains `review_queue`. Only observations classified against the persisted technical state as `new` or `updated` are included. `unchanged` observations remain in the run evidence but are not queued for semantic re-review.

GitHub Actions also persists a compact `review-queue.json` on the `ingestion-state` branch. This small handoff file is the preferred input for ChatGPT/`vacature-search`; it avoids reading the much larger full `latest.json` snapshot.

The intended handoff is:

`GitHub ingestion -> review-queue.json -> vacature-search canonical verification/CV evidence -> vacature-engine -> Vacature Register/output`

No candidate scoring happens inside ingestion.

## Source cadence

- `source-specs.live.json`: targeted ATS smoke/near-real-time sources, scheduled every six hours.
- `source-specs.daily.json`: slower public discovery feeds, scheduled once per day.
- `source-specs.deploy.json`: both classes together, used on ingestion-code deployments as an end-to-end smoke test.

This keeps slower/delayed feeds from being polled at the same cadence as targeted ATS sources while still proving all configured adapter classes on deployment.

## State

The runner keeps technical cross-run state in SQLite (`new`, `updated`, `unchanged`, `missing`, `closed`). In GitHub Actions this database is persisted on the dedicated `ingestion-state` branch, separate from code and policy.

Closure is conservative: a globally deduplicated vacancy closes only after every known source membership has met its own consecutive-missing threshold. A failed or partial source run never advances missing state.

## Google Sheet sync

The runner can update only source-health columns in `Bronnen` and append one compact technical row to `Runs`. It never bulk-writes raw jobs into `Vacatures`.

For GitHub Actions, configure repository secret `GOOGLE_SERVICE_ACCOUNT_JSON` with a Google service account that has editor access to the Vacature Register. If the secret is absent, the sync step exits successfully as `skipped`; ingest and GitHub technical state continue to work. The personal ChatGPT review workflow can still write candidate/run state through the existing Google Drive connection, so this secret is an optional technical-health mirror rather than a prerequisite for vacancy matching.

## Commands

```bash
python -m vacature_ingestion ingest-many --specs source-specs.live.json --state state.sqlite3 --out latest.json --allow-partial
python -m vacature_ingestion ingest-many --specs source-specs.daily.json --state state.sqlite3 --out latest.json --allow-partial
python -m vacature_ingestion export-state --state state.sqlite3 --health-out source-health.json
python -m vacature_ingestion sync-register --spreadsheet-id <ID> --summary latest.json --health source-health.json
python -m vacature_ingestion benchmark --count 10000
```

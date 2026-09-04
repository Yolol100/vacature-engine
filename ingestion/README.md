# Vacature Ingestion

Policy-free bulk ingestion component for the Webactueel vacature system. It converts public ATS/API/JobPosting data into `JobObservation 1.1` compatible observations and owns only technical ingest state.

## Boundaries

This component does **not** own candidate fit, WordPress relevance, salary/language/remote policy, application state, scoring or outreach. Those remain with `vacature-search`, the live Vacature Register and the deterministic `vacature_engine` package.

## Adapters

- Greenhouse public Job Board API
- Lever public Postings API
- Ashby public Job Postings API
- SmartRecruiters public postings API
- Generic public HTML pages exposing Schema.org `JobPosting` JSON-LD

## State

The runner keeps technical cross-run state in SQLite (`new`, `updated`, `unchanged`, `missing`, `closed`). In GitHub Actions this database is persisted on the dedicated `ingestion-state` branch, separate from code and policy.

Closure is conservative: a globally deduplicated vacancy closes only after every known source membership has met its own consecutive-missing threshold. A failed or partial source run never advances missing state.

## Google Sheet sync

The runner can update only source-health columns in `Bronnen` and append one compact technical row to `Runs`. It never bulk-writes raw jobs into `Vacatures`.

For GitHub Actions, configure repository secret `GOOGLE_SERVICE_ACCOUNT_JSON` with a Google service account that has editor access to the Vacature Register. If the secret is absent, the sync step exits successfully as `skipped`; ingest and GitHub technical state continue to work.

## Commands

```bash
python -m vacature_ingestion ingest-many --specs source-specs.live.json --state state.sqlite3 --out latest.json --allow-partial
python -m vacature_ingestion export-state --state state.sqlite3 --health-out source-health.json
python -m vacature_ingestion sync-register --spreadsheet-id <ID> --summary latest.json --health source-health.json
python -m vacature_ingestion benchmark --count 10000
```

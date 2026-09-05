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
- Workable public account jobs endpoint
- Personio public XML jobs feed

Daily secondary discovery feeds:
- Himalayas public JSON API with cursor pagination
- Jobicy public Remote Jobs API
- Remotive public API (24h-delayed; attribution metadata retained)

Secondary feeds remain discovery evidence. `vacature-search` must verify a promising role on the canonical employer/ATS page before eligibility and ranking.

## Review queue

Every `ingest-many` output contains the observations that changed in that ingestion. Only observations classified against persisted technical state as `new` or `updated` are nominated for semantic review; unchanged observations remain in run evidence without forcing semantic re-review.

GitHub Actions persists a compact `review-queue.json` plus `review-ack.json` on the `ingestion-state` branch. The compact queue is **at-least-once**: unacknowledged items from the previous snapshot are merged into the next queue, so a later ingestion cannot silently replace pending review work. Every queue item gets a stable `review_key` derived from strong vacancy identity plus its content hash. A content change therefore produces a new review key and requires a fresh semantic review.

To keep large queues connector-readable, the handoff stores an allowlisted technical summary plus a bounded plain-text description excerpt instead of the complete provider description. It also writes `review-queue-index.json` and bounded pages under `review-queue-pages/`, currently 25 items per page. Review consumers should read the index first and then only the page(s) they can safely process in that run. The full `review-queue.json` remains the canonical technical snapshot for ingestion merging; pages are a bounded read surface derived from it.

Full semantic eligibility still requires canonical employer/ATS verification; the queue excerpt is only discovery/triage evidence.

`review-ack.json` contains only technical acknowledgement keys and migration markers. It does not contain candidate policy or scoring. The ChatGPT review workflow should acknowledge every handled queue item, including cheap obvious non-relevant rejects, only after its intended review action has completed. A technical row already existing in `Runs` must never be treated as semantic acknowledgement.

The intended handoff is:

`GitHub ingestion -> review-queue-index.json -> bounded review-queue-pages/* -> vacature-search canonical verification/CV evidence -> vacature-engine -> Vacature Register/output -> review-ack.json`

No candidate scoring happens inside ingestion.

## Recovery

`review_backlog.load_review_backlog()` can rebuild pending review candidates from persisted SQLite first-seen state after a handoff failure. GitHub Actions only runs such a recovery when an explicit `ingestion/review-backlog-recovery.json` request is present and its migration ID is not already recorded in `review-ack.json`. Recovery is technical transport repair only; it does not decide vacancy relevance or candidate fit.

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

For GitHub Actions, configure repository secret `GOOGLE_SERVICE_ACCOUNT_JSON` with a Google service account that has editor access to the Vacature Register and enable the Google Sheets API for that service-account project. If the secret is absent, the sync step exits successfully as `skipped`; ingest and GitHub technical state continue to work.

## Commands

```bash
python -m vacature_ingestion ingest-many --specs source-specs.live.json --state state.sqlite3 --out latest.json --allow-partial
python -m vacature_ingestion ingest-many --specs source-specs.daily.json --state state.sqlite3 --out latest.json --allow-partial
python -m vacature_ingestion export-state --state state.sqlite3 --health-out source-health.json
python -m vacature_ingestion sync-register --spreadsheet-id <ID> --summary latest.json --health source-health.json
python -m vacature_ingestion benchmark --count 10000
```

# Vacancy Ingestion — Read-Only Source Adapters

This independent Python package retrieves public employer, ATS, API,
RSS and JobPosting data **only when explicitly requested**.

## Boundaries

1. Read current `Config` and the active `Bronnen` entries in the existing
   Vacature Register before acquisition. A registry access failure blocks scans.
2. Use permitted public source adapters. The repository's static
   `source-specs.*.json` are configuration *examples*, not a source registry.
3. Normalize observations without asserting vacancy authenticity, first
   publication date, language eligibility or candidate suitability.
4. The `vacature-search` skill verifies the actual role on the employer's
   official page and compares strong vacancy IDs with the Register.
5. Never write to the Register, send messages or apply automatically.
6. Technical `ingest` and `ingest-many` commands require `--spreadsheet-id`
   and read-only access to live `Bronnen`. Every requested provider and
   employer-bound source must be active. Partial approval, missing credentials
   and duplicate source IDs stop before HTTP fetches or SQLite state changes.

The local SQLite store is temporary technical state for explicit runs;
it is **not** an authoritative application or vacancy database.

## Packages and tests

- `src/vacature_ingestion/adapters/`: provider-specific public adapters.
- `src/vacature_ingestion/ats_resolver.py`: URL-to-ATS hints, not employer proof.
- `src/vacature_ingestion/runner.py`: safe snapshots and observation history.
- `cli.py`: bounded, explicitly invoked technical commands.
- `tests/`: offline unit, security and regression tests.

The deterministic scoring and eligibility engine lives separately in the
repository root package `src/vacature_engine/`.

## Bounded Working Nomads source

The active `working-nomads` registry ID can use the existing `publicfeeds`
adapter against its fixed public `/api/exposed_jobs/` endpoint. The feed is
an observed, bounded subset, **not** a complete employer or job catalog.
Only board-hosted job/go URLs are accepted. The provider's `pub_date`
remains metadata, not an independently verified employer posting date.
`remote` and `apply_url` remain unknown until the specialist validates
the exact official vacancy. GitHub never schedules this adapter.

Remote Jobs/Remote.com is scheduled to close on 30 November 2026. A bounded
on-demand inspection of `jobs.remote.com` may use the existing `jsonld`
adapter with approved current detail URLs, but does not justify a permanent
provider-specific scraper or source closure before official confirmation.

## Optional free Google discovery

The `serpapi_google` adapter retrieves organic Google results through a
**verified free SerpApi plan**; the key never belongs in code or committed
configuration. Only the registered `google-jobs` discovery source is allowed.
Search hits are *not* final verified vacancies and are never complete
snapshots for vacancy closure.

GitHub Actions retains offline regression tests. Additionally, the owner
expressly approved a 30-minute **public-only browser discovery worker**.
It uses the existing SerpApi secret ONLY after a free-plan account check and
only at a 4-hour search slot. It never scrapes Google Search directly. It
scans sanitized
public source URLs and publishes only public job observations to a
separate branch. Private Apps Script ingests and deduplicates pending leads.
Official vacancy/NL eligibility verification remains on-demand.
See \`docs/SCHEDULED-30M-BROWSER-WORKER.md\`.
The approved public workflow also starts an ephemeral, localhost-only
SearXNG Docker instance after checkout for free multi-engine discovery.
Google may remain blocked, while DuckDuckGo, Bing or Brave can return
role-specific links. Each result is still unverified, and blocked original
job sites remain marked as such. No access-control evasion or paid API.


See [FREE-GOOGLE-DISCOVERY.md](docs/FREE-GOOGLE-DISCOVERY.md).

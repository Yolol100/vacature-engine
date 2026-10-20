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

## Optional free Google discovery

The `serpapi_google` adapter retrieves organic Google results through a
**verified free SerpApi plan**; the key never belongs in code or committed
configuration. Only the registered `google-jobs` discovery source is allowed.
Search hits are *not* final verified vacancies and are never complete
snapshots for vacancy closure.

GitHub Actions contains only offline tests. The only user-facing vacancy
search entrypoint is an explicit ChatGPT `vacature-search` request. The
optional free Google adapter remains source-gated and must not be scheduled
or launched through GitHub Actions.

See [FREE-GOOGLE-DISCOVERY.md](docs/FREE-GOOGLE-DISCOVERY.md).

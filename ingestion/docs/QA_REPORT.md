# QA report - vacature-ingestion 0.9.0

Status: implementation gates require unit/integration tests, compileall, 10,000-record benchmark and GitHub-hosted target-runtime ingestion. Final live evidence is recorded only after the merged main workflow succeeds.

Current controls:
- isolated sibling package with zero third-party Python runtime dependencies;
- Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Personio, generic JobPosting JSON-LD, Himalayas, Jobicy and Remotive adapters;
- provider pagination, bounded HTTP/retries and response limits;
- strong identity, content hashing and SQLite cross-run state;
- immutable content-hash vacancy snapshots;
- multi-source-safe closure and source health;
- live `Bronnen.status` gating before acquisition, including optional concrete employer-row binding;
- at-least-once semantic review queue with race-safe ACK merge, recovery migration, 25-item pages and backlog-age telemetry;
- direct Google Sheet source-health/technical-run sync through the configured service account;
- scheduled GitHub Actions with isolated `ingestion-state` persistence.

Regression coverage includes source failure isolation, pagination, malformed provider shapes, strong/weak identity behavior, missing/close thresholds, source health, persistent review carry-over, ACK pruning, content-change re-review, paginated handoff, stale-page cleanup, backlog recovery, ACK race merging, Register-owned source filtering and immutable snapshot history.

Repository-level assurance additionally runs Python 3.11-3.14 unit tests, controlled mutation smoke, reproducible release-bundle comparison, CodeQL and release SBOM/provenance attestations.

Explicitly excluded: candidate scoring/policy, automatic source-priority mutation, application submission and unnecessary Redis/Kafka/Celery worker infrastructure.

Claim boundary: green CI proves technical assurance only. Candidate fit, vacancy open status and application decisions still require the live `vacature-search` canonical verification flow. A formal cryptographic release-verification claim requires independent verification of the produced GitHub attestation.

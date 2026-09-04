# QA report - vacature-ingestion 0.2.0

Status: local implementation gates pass. GitHub-hosted live network execution is the target-runtime gate.

Implemented: isolated sibling package, zero Python runtime dependencies, Greenhouse/Lever/Ashby/SmartRecruiters plus generic JobPosting JSON-LD adapter, pagination, bounded HTTP/retries, strong identity, content hashing, SQLite cross-run state, multi-source-safe closure, source health, optional compact Register sync, scheduled GitHub Actions and isolated ingestion-state branch.

Latest local controlled-runtime verification: 35/35 unit/integration tests green, compileall green, 10,000 synthetic records processed in about 0.7 seconds.

Explicitly excluded: candidate scoring/policy, application submission, automatic source-priority mutation and unnecessary Redis/Kafka/Celery worker infrastructure.

Google Register sync remains fail-safe skipped until `GOOGLE_SERVICE_ACCOUNT_JSON` is configured. The GitHub workflow preserves technical state before enforcing its final live-ingestion threshold, so failure evidence is not lost.

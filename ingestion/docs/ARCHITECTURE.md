# Architecture boundary

## Ownership

The runner owns public read acquisition, source-specific parsing, bounded normalization, JobObservation 1.1-compatible output, strong technical identity, content hashing/change detection, per-source run evidence and safe missing/closed lifecycle state.

It does not own discovery priorities, WordPress relevance, candidate fit/evidence scoring, remote/language/salary eligibility policy, Applications, outreach or submission.

## Identity

Strong keys only:
1. normalized canonical URL when available;
2. `source_id + source_job_id`.

Provider account/board is prefixed into `source_job_id`. Employer/title/location is only a weak duplicate-candidate fingerprint and never authorizes a merge.

## Lifecycle

A successful complete snapshot resets missing state for observed memberships. Failed/partial runs never increment missing state. A globally deduplicated job closes only when every known source membership has reached its configured missing threshold, which prevents one stale or failing source from closing a vacancy still visible elsewhere.

## Scaling

The runner starts as one bounded process with provider pagination and SQLite state. Local controlled-runtime tests process 10,000 synthetic observations in under one second, so distributed queues/workers are not justified yet. Target-runtime network throughput is measured in GitHub Actions.

## Source roster

The runner consumes known provider board/account specifications. Discovery of new board slugs remains upstream in `vacature-search` and registered sources; this runner does not become a second discovery-policy owner.

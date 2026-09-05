# Architecture boundary

## Ownership

The runner owns public read acquisition, source-specific parsing, bounded normalization, JobObservation 1.1-compatible output, strong technical identity, content hashing/change detection, immutable content snapshots, per-source run evidence and safe missing/closed lifecycle state.

It does not own discovery priorities, WordPress relevance, candidate fit/evidence scoring, remote/language/salary eligibility policy, Applications, outreach or submission.

The live `Vacature Register` owns source activation. Repository source specs are technical board/account targets only. Before live acquisition, GitHub Actions reads `Bronnen` and retains only specs whose provider source row is `active`; specs with `options.registry_source_id` also require that concrete employer row to be active. Register read failure is fail-closed.

## Identity

Strong keys only:
1. normalized canonical URL when available;
2. `source_id + source_job_id`.

Provider account/board is prefixed into `source_job_id`. Employer/title/location is only a weak duplicate-candidate fingerprint and never authorizes a merge.

## History

`jobs` stores current technical state. `job_snapshots` retains one immutable payload per `(job_id, content_hash)` with first/last seen timestamps. Unchanged observations extend last-seen without creating duplicates; changed content creates a new historical snapshot. Snapshot state follows strong-identity merges.

## Lifecycle

A successful complete snapshot resets missing state for observed memberships. Failed/partial runs never increment missing state. A globally deduplicated job closes only when every known source membership has reached its configured missing threshold, which prevents one stale or failing source from closing a vacancy still visible elsewhere.

The semantic review handoff is at-least-once. Pending items persist until their `review_key` is explicitly acknowledged. The queue is paginated for bounded connector reads and exposes backlog age/count telemetry.

## Scaling

The runner starts as one bounded process with provider pagination and SQLite state. Controlled-runtime tests process 10,000 synthetic observations quickly enough that distributed queues/workers are not justified. Target-runtime network throughput and end-to-end source gating are measured in GitHub Actions.

## Source roster

The runner consumes known provider board/account specifications after live Register activation filtering. Discovery of new board slugs remains upstream in `vacature-search` and registered sources; this runner does not become a second discovery-policy owner.

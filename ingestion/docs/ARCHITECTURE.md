# Architecture boundary

## Ownership

The runner owns public read acquisition, source-specific parsing, bounded normalization, JobObservation 1.1-compatible output, strong technical identity, content hashing/change detection, immutable content snapshots, per-source run evidence and safe missing/closed lifecycle state.

It does not own discovery priorities, WordPress relevance, candidate fit/evidence scoring, remote/language/salary eligibility policy, Applications, outreach or submission.

The live `Vacature Register` owns source activation. Repository source specs are technical board/account targets only. Before an explicitly requested scan, the caller checks the live `Bronnen` tab. Only sources with `active` status qualify; specs bound to an employer also require an active matching employer row. Failure to read the Register blocks acquisition.

## Identity

Strong keys only:
1. normalized canonical URL when available;
2. `source_id + source_job_id`.

Provider account/board is prefixed into `source_job_id`. Employer/title/location is only a weak duplicate-candidate fingerprint and never authorizes a merge.

## History

`jobs` stores current technical state. `job_snapshots` retains one immutable payload per `(job_id, content_hash)` with first/last seen timestamps. Unchanged observations extend last-seen without creating duplicates; changed content creates a new historical snapshot. Snapshot state follows strong-identity merges.

## Lifecycle

A successful **verified complete** provider snapshot resets missing state for observed memberships. Failed, capped or partial runs never increment missing state. Employer ATS adapters can report full coverage only when the result count is below `max_jobs`. Public search results, moving APIs, bounded feeds, RSS and single-page JSON-LD extraction are **not** proof that missing jobs have closed. A globally deduplicated job closes only when every known authoritative source membership reaches its configured missing threshold. Always verify canonical employer evidence before treating a technical closure as real.

There is no persistent background review queue. The caller directly checks observed vacancies against the live Register, validates the official job page and candidate-fit evidence, and decides what is new.

## Scaling

The runner starts as one bounded process with provider pagination and SQLite state. Controlled-runtime tests process 10,000 synthetic observations quickly enough that distributed queues/workers are not justified. Source reachability and verification must be checked at the time of a user-requested scan; historical GitHub run results are not current evidence.

## Source roster

The runner consumes known provider board/account specifications after live Register activation filtering. Discovery of new board slugs remains upstream in `vacature-search` and registered sources; this runner does not become a second discovery-policy owner.

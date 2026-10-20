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

A valid authoritative empty jobs collection may confirm there are no current postings. An absent or invalid collection in a provider response is instead a failed run; it must never be interpreted as proof that all jobs have closed.

A successful **verified complete** provider snapshot resets missing state for observed memberships. Failed, capped or partial runs never increment missing state. Employer ATS adapters can report full coverage only when the result count is below `max_jobs`. Public search results, moving APIs, bounded feeds, RSS and single-page JSON-LD extraction are **not** proof that missing jobs have closed. Incomplete sources never gain a closure-voting membership; stale memberships from previous bounded-feed runs are cleaned up. When an exact role also exists on a full-coverage employer ATS, its authoritative payload and closed status take precedence over later third-party discovery hits. A globally deduplicated job closes only when every known authoritative source membership reaches its configured missing threshold. Always verify canonical employer evidence before treating a technical closure as real.

There is no persistent background review queue. The caller directly checks observed vacancies against the live Register, validates the official job page and candidate-fit evidence, and decides what is new.

## Scaling

The runner starts as one bounded process with provider pagination and SQLite state. Controlled-runtime tests process 10,000 synthetic observations quickly enough that distributed queues/workers are not justified. Source reachability and verification must be checked at the time of a user-requested scan; historical GitHub run results are not current evidence.

## Source roster

The runner consumes known provider board/account specifications after live Register activation filtering. Discovery of new board slugs remains upstream in `vacature-search` and registered sources; this runner does not become a second discovery-policy owner.

## Technical CLI source gate

`python -m vacature_ingestion ingest` and `ingest-many` are optional
technical adapters, never an alternative user-facing vacancy-search route.
Both require `--spreadsheet-id` and working read-only Google Register access.
All requested source IDs and employer bindings must be active in `Bronnen`;
if any one is blocked, no source request or SQLite mutation may begin.
Missing credentials and ambiguous registry IDs fail closed. No search
scheduling or automatic application is possible through these commands.

## Verified final ranking admission

Only `final_review.validate_assessment` may turn a review candidate into an
internal `_ValidatedRankingInput`. That gate binds the exact official ATS role,
employer ownership, current visible official page, original posting date,
Netherlands remote execution, employer languages, private CandidateEvidence,
requirements and anchored specialist scoring to live policy and proof digests.

`official_review.rank_fully_verified` accepts only that in-memory handoff with
a current matching review date and all five SHA-256 context fields. Raw ATS,
search, JSON or public feed records — including invented scores or self-claimed
`authenticity=verified` — cannot reach final ranking. This is a structural
defense-in-depth check, not a second semantic verifier or a new set of proof
states. The deterministic engine weights and thresholds remain unchanged.
No public GitHub workflow is used for vacancy search.

## Negative-only regular travel gate

A Remote label cannot override clear first-party requirements for regular
customer/site travel. The specialist's final-review preflight blocks a
quantified, non-ambiguous travel load of at least 20% (e.g. 30-50% onsite
customer deployments) using substantial_required_travel before final scoring.
This check does not positively verify other roles as fully remote and does not
automatically reject isolated team offsites, uncertain 'up to' bounds, or
unrelated compensation percentages. Original dates, employer ownership,
candidate evidence and all other official hard gates remain required.

The travel-% detector ignores optional attendance and compensation-only travel
percentages (costs, expenses, reimbursements, discounts and subsidies). This
prevents synthetic travel-expense examples from blocking otherwise verified
remote roles. Hard-required 30-50% client-site engagement remains blocked.

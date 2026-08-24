# Architecture

## Rule ownership

- ChatGPT Skill: workflow, evidence precedence, semantic verification, user-specific profile truth and side-effect gates.
- Google Drive: mutable source registry, vacancy/application history, run metrics and current versions.
- `vacature-engine`: deterministic normalization, IDs/hashes, arithmetic, public adapters and contract tests.
- Web/ATS: current external evidence.
- Outlook: draft side effect only after the Skill's application gate.

## Data path

`public source -> adapter/JSON-LD -> JobRecord/evidence -> deterministic dedupe/recency -> Skill canonical verification -> gates/score -> optional application package -> Outlook draft -> Drive readback`

## Adapter contract

Every adapter accepts one employer/board slug and returns `list[JobRecord]`. Adapters do not decide whether a job fits the user. Unknown values remain `None`; adapters do not invent dates, countries, remote status or salary.

## Failure contract

Failures map to the same categories used by the Skill/Drive source registry. Transient failures can be retried with bounded backoff. Blocked/authenticated access stops. This keeps source health observable and prevents silent bypasses.

## Extension rule

Before adding an adapter:

1. Prefer an official public endpoint or feed.
2. Verify it currently works without user credentials.
3. Add fixture tests before enabling it.
4. Preserve unknown fields instead of guessing.
5. Add it to `AdapterRegistry`; callers never import provider classes by path.
6. Keep browser rendering as fallback, never as the first path for a structured public API.

## Release verification method

Treat readiness as layered evidence rather than one headline score:

1. **Contract** — Skill, Drive and repo each own one class of truth.
2. **Deterministic** — unit, regression and Skill↔repo parity tests pass.
3. **Dependency/live** — public-source assumptions and GitHub Action pins are rechecked against current official sources.
4. **State** — Drive schema/version writes are read back.
5. **Runtime** — a real candidate must still pass best-available live-listing freshness, remote/NL and duplicate verification; use employer/original evidence for conflicts, gaps or application-route recovery and never manufacture a positive golden path.

A build/configuration audit and a real vacancy-run proof are separate claims.

## Date semantics

`posted_at` is reserved for a timestamp safe enough to test the original <=7-day gate. Provider update/release/last-published fields live in `source_date` with explicit `source_date_semantics` and cannot silently become original-age proof. Unknown remains unknown.

## Determinism under concurrency

Sources may fetch concurrently, but results are flattened in configured source order before deduplication. This makes duplicate preference reproducible and lets Drive source priority remain meaningful.

# Architecture

## Rule ownership

- ChatGPT Skill: workflow, evidence precedence, semantic verification, user-specific profile truth and side-effect gates.
- Google Drive: mutable source registry, vacancy/application history, run metrics and current versions.
- `vacature-engine`: deterministic normalization, IDs/hashes, arithmetic, public adapters and contract tests.
- Web/ATS: current external evidence.
- Outlook: draft side effect only after the Skill's application gate.

## Data path

`public source -> adapter -> JobRecord -> dedupe/recency -> Skill canonical verification -> gates/score -> optional application package -> Outlook draft -> Drive readback`

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

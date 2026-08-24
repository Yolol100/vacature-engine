# Changelog

## 3.1.0 - 2026-08-25

- Hardened all numeric/type gates against booleans, NaN/infinity, invalid blocking flags and future dates.
- Tightened seniority: generic Engineer no longer proves medior+, and junior/intern/trainee/graduate/entry-level roles fail.
- Added deterministic same-source and semantic deduplication with stable source-order results under concurrency.
- Added source-date semantics: Greenhouse `first_published`, Lever creation time, and conservative Ashby/SmartRecruiters handling.
- Updated Personio to current `.jobs.personio.com` XML/job URLs and added SmartRecruiters pagination.
- Added official `JobPosting` JSON-LD evidence extraction with bounded block size.
- Hardened public HTTP/browser access: pre-request host/port/credential checks, manual redirects, HTTPS downgrade blocking, response limits and one-retry maximum.
- Hardened application guard with role-authorized recipient, HTTPS evidence source, valid email, selected/ready CV and exact-subject checks.
- Expanded release audit to 88 unit tests plus 400 adversarial/metamorphic scenarios and direct Skill parity checks.

## 3.0.2 - 2026-08-25

- Updated GitHub Actions to current verified full-SHA releases of checkout v7.0.1 and setup-python v7.0.0.
- Added a repeatable `scripts/release_check.py` release gate for structure, SHA pins, least privilege, compilation, tests and Ruff.
- Expanded regression coverage for US-only, stale postings, prompt-injection-shaped input, unsupported application claims, material content changes and unknown salary.
- Clarified that build readiness and live vacancy verification are separate claims.
- Clarified SmartRecruiters authentication ambiguity: the project never supplies credentials and fails closed if anonymous public reads are rejected.

## 3.0.1 - 2026-08-25

- Fixed Ruff/import formatting found by the first GitHub Actions run; no logic change.

## 3.0.0 - 2026-08-25

- Added normalized `JobRecord` schema and adapter registry.
- Added keyless Greenhouse, Lever, Ashby, SmartRecruiters and Personio adapters.
- Added shared public HTTP retries/backoff, error mapping and cross-host redirect protection.
- Added bounded multi-source fetching, deduplication and recency helpers.
- Added application-guard parity with the ChatGPT Skill.
- Added JSON CLI and optional `ats-scrapers` public-catalog bridge.
- Added Dependabot, Python 3.11-3.13 CI matrix, architecture/security docs and expanded regression/parity tests.
- Explicitly excluded proxy rotation, stealth/TLS impersonation, login/CAPTCHA bypass and automatic applications.

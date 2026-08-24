# Changelog

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

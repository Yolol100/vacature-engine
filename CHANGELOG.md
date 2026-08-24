# Changelog

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

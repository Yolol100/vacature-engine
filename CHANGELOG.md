# Changelog

## 3.4.0 - 2026-08-25

- Added explicit fail-closed type handling for work eligibility, seniority and application-stage inputs so malformed values cannot be coerced into a valid state or raise unintended type errors.
- Added a deterministic `motivation_qa_pass` requirement for Outlook/email draft readiness, aligning the code guard with the Skill's evidence-bank, swap, reuse and name-masked anti-template checks.
- Expanded the adversarial scenario audit to combinatorial gate, scoring and application matrices, including `stale_repost`, motivation QA, invalid types, URL/hash invariants, recency, public-target safety and JobPosting semantics.
- Kept scoring weights, worldwide discovery policy and search qualification semantics unchanged.

## 3.3.0 - 2026-08-25

- Added an explicit backwards-compatible `stale_repost` hard-gate input so evidence-backed recycled/re-dated vacancies fail deterministically instead of relying only on prose policy.
- Added regression coverage for stale-repost blocking, legacy absence/default behavior and invalid input types.
- Kept duplicate and freshness semantics unchanged: the workflow must still establish semantic repost evidence before setting the new blocker.

## 3.2.0 - 2026-08-25

- Generalized location semantics for worldwide-remote discovery: prefer `work_eligibility` and `work_eligibility_certainty` while preserving legacy Netherlands-specific inputs.
- Added a generic incompatible-geography blocker while keeping the legacy US-only flag compatible.
- Separated search qualification from application readiness: `plausible` work eligibility may remain discoverable, but application preparation now requires explicit work-eligibility confirmation.
- Added a mandatory legitimacy check before application preparation/drafting so unresolved employer/recruiter/domain/payment risk cannot reach an application-ready state.
- Expanded parity and scenario coverage for worldwide eligibility aliases, generic geography blockers, eligibility confirmation and legitimacy checks.

## 3.1.1 - 2026-08-25

- Allow established live job-board listings to satisfy active/link gate evidence without requiring an employer/ATS duplicate.
- Add generic `posting_active` / `listing_link_working` inputs while preserving the legacy official-key inputs.
- Relax the draft-recipient provenance rule from official-source-only to any verified HTTPS recruitment/application-relevant published source; keep syntactic email and explicit relevance checks.
- Preserve no-email candidates for manual Indeed/LinkedIn/external-form handoff instead of treating missing email as a vacancy failure.
- Add regression/scenario coverage for job-board-only evidence, no-email prepare/manual handoff and backward compatibility.

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

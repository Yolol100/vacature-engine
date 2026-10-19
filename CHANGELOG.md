# Changelog

## Ingestion 0.12.0 - 2026-10-19
- Hardened optional free Google discovery: strict active Free Plan and quota checks, round-robin pagination, canonical URL deduplication and safe handling of invalid links.
- Moved snapshot completeness to the adapter contract; partial Google discovery cannot close vacancies, even through direct ingestion calls.
- Added a manual-only GitHub Actions workflow with a zero-search account check and bounded discovery modes. No scheduler, automated applications or Register writes.
- Added broader adversarial tests for quota, key handling, paging, duplicate results, unsafe URLs and lifecycle state.
- Brought the ingestion adapter release manifest and both Python regression suites back into sync.

## Engine 5.8.0 - 2026-10-02
- Added `web_design_development` as the third configurable target role family for web design, website UX/UI, frontend, accessibility, performance, technical SEO and broader web development when the web component is material.
- Kept `wordpress_ecosystem` and `ai_workflow_automation`. General product design, unrelated software engineering and AI/ML positions without material web or workflow requirements remain out of scope.
- Added `web_design_related=true` as a caller signal alongside explicit `role_families`.
- Kept fully remote, compatibility with work from the Netherlands, language and salary/data integrity checks, score anchors and minimum-fit thresholds unchanged.
- Added regressions for qualifying web development/design roles and rejection of unrelated product design.

## Engine 5.7.0 - 2026-09-29
- Added runtime-configurable role families through `target_role_families`.
- Expanded `wordpress_ecosystem` with `ai_workflow_automation` for AI workflows, automation, integrations, agents and GenAI operations.
- Excluded generic AI/ML and data-science roles without material automation or workflow requirements.
- Preserved backward-compatible WordPress-only behaviour when no `target_role_families` setting is supplied.
- Kept remote, Netherlands workability, language and salary integrity, score anchors and minimum-fit constraints unchanged.
- Added regressions for AI-workflow acceptance, unrelated AI rejection, explicit families and unknown families.

## Historical Unreleased - 2026-09-25
- Documented the caller-owned bilingual application pack: Dutch and English CV/cover-letter content from one evidence set, with the official application language taking precedence.
- Excluded named projects, cases and repositories from CV bodies. At most three verified work-sample links are allowed in a cover letter when relevant or requested.
- Identified the canonical portfolio index as `https://andrewbaeten.nl/category/cases`. Never guess case slugs or repositories.
- Standard sign-off uses `Andrew` only: Dutch `Vriendelijke groet,`; English `Kind regards,`.
- No changes to eligibility, ranking, source priority, candidate inference or automatic submission boundaries.

## Engine 5.6.1 - 2026-09-15
- Documented the caller-owned Form Application Pack boundary for verified employer/ATS forms.
- Allowed Vacature Search to prepare the exact vacancy title, visible form questions with evidence-bound draft answers, and a vacancy-specific CV.
- Salary expectations, work authorization, legal/sensitive/current-state fields still require human confirmation; assessments and explicitly AI-prohibited responses remain manual.
- The engine remains form-free and policy-free: no browsing, answer prose, accounts, CAPTCHA circumvention or automatic applications.

## Engine 5.6.0 - 2026-09-07
- Added CV Artifact Contract v1.0 for deterministic DOCX filenames tied to exact vacancies, SHA-256 provenance for source CV and vacancy snapshots, and stable artifact identities.
- The helper remains policy-free: no CV prose, experience inference, document generation, discovery or auto-apply.
- Added regressions for stable names, vacancy isolation, URL/hash validation and fail-closed artifact manifest readback.
- Left existing remote-first v12 gates, score anchors, salary rules, opportunity scoring and rankings unchanged.

## Engine 5.4.1 - 2026-09-06
- Restored the live salary preference rule from the Vacature Register: verified salaries below `min_monthly_salary_eur` produce a `salary_below_preference` warning rather than automatic exclusion.
- A verified range fully below preference remains advisory; unknown salaries remain a warning/fallback.
- Invalid, non-finite, conflicting or reversed salary inputs still fail closed with `salary_invalid`.
- The ranking benchmark includes at least 30 labelled cases and preserves advisory salary behaviour alongside score anchors and hard gates.

## Engine 5.4.0 - 2026-09-04
- Upgraded the observation contract to v1.1: canonical URL and `source_id + source_job_id` are the only automatic strong identity keys.
- Employer/title/location remains a weak duplicate-candidate fingerprint and must not automatically merge distinct strong identities.
- Canonicalization now exposes `published_at_candidates`, `published_at_conflict`, source types and duplicate-candidate metadata for semantic verification by the Skill.
- Malformed URL ports fail closed rather than crashing runs.
- Added dependency-free `jobposting_signals()` for conservative Schema.org `JobPosting` evidence: dates, TELECOMMUTE, permitted applicant locations, employment type, direct apply and raw salary fields.
- Structured data never overrides Skill/Config authority for open status, remote geography, salary normalization or candidate fit.
- Added regressions for false merges, corrupt URLs, publication-date conflicts and structured-data boundaries.

## Engine 5.3.0 - 2026-08-30
- Added runtime language gating via `allowed_listing_languages`. The current `vacature-search` workflow supplies `nl,en` from live Config.
- When active, vacancy text and the application flow must be in a permitted language, and no additional mandatory working language may be required.
- Missing language evidence fails closed when the language gate is active; existing callers without language configuration remain backward-compatible.
- Added Dutch/English, third-language listing and application-flow regression cases.

## Engine 5.2.0 - 2026-08-28
- Clarified worldwide remote discovery: the Skill searches globally, while the engine admits only roles practically and legally workable from the Netherlands, including payroll and time-zone constraints.
- Removed the calendar-year gate. Verified posting age is compared directly with `max_posting_age_days`.
- Added salary ranges through `salary_min_monthly_eur` and `salary_max_monthly_eur`; the historical rule at this release rejected only a verified range entirely below preference.
- Simultaneous exact salary and range values, reversed ranges, and invalid/non-finite amounts fail closed with `salary_invalid`.
- Added regressions for year boundaries, worldwide compatibility and salary ranges. Score anchors and minimum scores were unchanged.

## Engine 5.1.0 - 2026-08-26
- Invalid salary data now fails closed: only explicit `null` is unknown; strings, booleans and non-finite numbers are `salary_invalid`.
- Publication dates accept only ISO dates or datetimes, blocking appended-suffix smuggling.
- Added contemporary golden, property/metamorphic, adversarial and controlled mutation tests.
- Added reproducible source release evidence with SPDX 2.3 SBOM, package verification, SHA-256 and provenance receipts.
- Added CodeQL, Dependabot, deterministic dependency-policy checks, CODEOWNERS, PR template and SECURITY.md. Dependency Review was not available while the repository Dependency Graph was disabled. These items describe that historical release, not current active workflows.
- The historical Release Evidence workflow used artifact attestations with fully pinned action commit SHAs.
- Pinned the build backend to `setuptools==84.0.0` for reproducible build inputs.

## Engine 5.0.0 - 2026-08-26
- Removed mutable gate and output thresholds from Python constants. Callers must supply them through live Config.
- Added `VacancyPolicy` and `policy_from_config()` with validation of six required runtime values and fail-closed handling of absent or invalid Config.
- The CLI now accepts explicit `today`, `policy` and `vacancies`, replacing a broken implicit call without `today`.
- Added regressions proving that salary, posting age, output limit and score thresholds affect engine results.
- Removed duplicate runtime-threshold constants from public package exports.

## Engine 4.0.5 - 2026-08-26
- Used a dynamic `today.year` instead of a hardcoded 2026 for the calendar-year gate at that time.
- Non-finite salaries no longer counted as known.
- Invalid individual records were skipped without blocking whole batches.
- Added coverage for year changes, non-finite salaries, malformed records and newest-first tie-breaking.
- Equal candidates receive a stable canonical URL/title tie-break independent of input order.

## Engine 4.0.4 - 2026-08-26
- Required an explicitly supplied `today` from the canonical Config timezone rather than an implicit host date.
- Historical CI tested Python 3.11–3.14 with pinned GitHub Actions. This is historical release information.

## Engine 4.0.3 - 2026-08-26
- Restricted output to strong matches: score at least 75, core fit at least 40 and evidence fit at least 10.
- Added regressions blocking weak known-salary matches and guarding the 75-point boundary.

## Engine 4.0.2 - 2026-08-26
- Synchronized score anchors, recency points and tie-breaks between the repository and the Skill.
- Simplified the README without functional changes.

## Engine 4.0.1 - 2026-08-25
- Allowed unknown salary only as a fallback with a score of at least 75/100.
- Extended boundary and ranking tests.

## Engine 4.0.0 - 2026-08-25
- Reduced the repository to one simple filter/rank helper.
- Kept only hard filters, simple scoring and top-ten selection; removed scraping, application logic and auditing from the then-current engine.

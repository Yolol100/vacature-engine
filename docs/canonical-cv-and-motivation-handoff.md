# Reusable canonical CV and inline motivations — vacancy handoff

**Owner:** `vacature-search` specialist under `webactueel-workflow`. **Authoritative policy:** live Google Drive Vacature Register `Config`, `Bronnen`, `CandidateEvidence`, `Applications`, `Feedback`, and `JobSnapshots`. This document is explanatory, not a competing registry.

## User-requested vacancy search output (2026-11-07)

1. Run only on an explicit vacancy-search request. Respect existing official employer/ATS, original-date, remote-from-Netherlands, language, role-fit, authenticity, and deduplication checks. Show fewer results rather than unverified vacancies.
2. Resolve `Config.canonical_cv_file_id` and `Config.canonical_cv_name` **at run time**. Reuse that exact verified Drive document for every normal shortlist, regardless of the listing website; **do not generate or tailor a different CV for each role**. If an employer explicitly requires a different language/file type, flag the exception and follow the user's authorization and employer requirements. Do not silently modify the canonical source.
3. After each *verified* vacancy, place the official role title/employer/URL and **exactly two short, copyable motivation paragraphs directly in chat**:
   - Paragraph 1: employer-specific fit supported by actual skills and live job requirements.
   - Paragraph 2: one traceable project or contribution and the portfolio link read from `Config.application_pack_portfolio_url`.
   - Match the official listing language. Do not output DOCX/PDF motivation files, imaginary case links/percentages, or generic unverified fit.
4. After all vacancies, show the **same registered canonical CV** exactly once, with its verified Google Drive link and a download link only if a real session-backed file exists.
5. Never submit applications or send emails. Never change historical application status without actual evidence. Keep `vacature-engine` as **deterministic gates/ranking**, not a prose generator.

## Data and provenance boundaries

- Canonical CV/portfolio facts: 10 years of WordPress experience, 90 delivered projects, 120 managed websites/stores, and only technology/project work corroborated by the CV, candidate evidence, portfolio and specific repository READMEs.
- GitHub repositories can demonstrate source capabilities; do not claim experimental/source-only tooling is production deployed.
- YouTube transcripts offer optional communication heuristics; comments are anecdotes, not candidate-experience or ATS policy facts.
- Use original listing publication dates, not aggregator timestamps or latest update dates.
- Default motivation is plain chat text and not an automatic application.
- Source of truth for links/version must be **Drive Config**, never a pinned file ID in GitHub.

## Regression scenarios to check

1. Four verified remote NL matches: four pairs of motivation paragraphs and one canonical CV link.
2. Hybrid, US-only or outdated role: no entry and no motivation.
3. Former application/rejection: deduplication suppresses it.
4. Insufficient CandidateEvidence: do not invent skill, metric or case.
5. CV on Drive has been replaced: always resolve new Config ID.
6. Employer needs PDF/other language: follow employer requirement; do not alter canonical CV silently.
7. Missing Drive file/readback: show verification blocker, not a fabricated link.
8. A run with no verified roles: say so clearly; do not fabricate any motivations.

**Implementation note:** Configuration and chat instructions own this presentation contract. No source-code change or GitHub Actions scheduling is required in the deterministic vacancy engine.

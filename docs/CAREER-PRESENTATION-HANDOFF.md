# Career presentation handoff

Last reviewed: 2026-09-19.

This document records the boundary between deterministic vacancy-engine logic and caller-owned CV/portfolio presentation guidance. It is documentation only: it does not add scoring, generation or candidate inference to `vacature_engine`.

## Ownership

- `vacature-search` owns evidence-bound CV tailoring, recruiter/job-search guidance and employment portfolio/case-study semantics.
- The design/commercial owner owns visual presentation and client-acquisition UX when a portfolio serves customers as well as employers.
- `vacature-engine` continues to own only deterministic vacancy selection helpers, ingestion boundaries and CV artifact metadata/provenance.
- The engine must never rewrite job titles, generate resume/portfolio prose, infer candidate experience, invent results, or score the visual quality of a portfolio.

## Validated presentation guidance

The caller may use these bounded rules without moving them into engine runtime logic:

1. Optimize CVs for a brief initial human scan, but do not treat “6 seconds” or “7.4 seconds” as a universal recruiter timing law.
2. Preserve official job titles. A parenthetical functional clarification is allowed only when factually equivalent and evidence-backed.
3. Remove repetitive profile/skills/value content when it consumes scan time without adding evidence.
4. Project/case-study evidence should expose context/problem, candidate contribution, relevant stack/capabilities, decisions, proof and a verified result or learning.
5. Portfolio visuals should prove something. Prefer clearly captioned shipped screens, real before/after evidence, flows/wireframes when relevant, code/repository, QA/performance/accessibility evidence and live deliverables over decorative mockups alone.
6. Separate project/context facts from candidate-attributable outcomes. A number or badge is not a result unless attribution is supported.
7. No verified metric is required: a specific qualitative result is valid when it describes what shipped, was validated, enabled or improved.
8. Mixed recruiter/client portfolios should share one evidence-bound project core while allowing audience-specific scan layers and calls to action.

## Evidence reviewed

- Harvard MCS, 2026 industry resume guidance:
  https://careerservices.fas.harvard.edu/blog/2026/09/15/resumes-for-industry-grad-student-edition-2026/
- Greenhouse resume parsing guidance:
  https://support.greenhouse.io/hc/en-us/articles/200989175-Unsuccessful-resume-parse
- Wingate et al. (2025), International Journal of Selection and Assessment:
  https://onlinelibrary.wiley.com/doi/10.1111/ijsa.70022
- Nielsen Norman Group, UX portfolio guidance:
  https://www.nngroup.com/articles/ux-design-portfolios/
- Nielsen Norman Group, hiring-manager portfolio research summary:
  https://www.nngroup.com/videos/ux-portfolios-hiring/
- GitHub Docs, using a GitHub profile to enhance a resume:
  https://docs.github.com/en/account-and-profile/tutorials/using-your-github-profile-to-enhance-your-resume
- Historical Ladders 2018 eye-tracking release:
  https://www.prnewswire.com/news-releases/ladders-updates-popular-recruiter-eye-tracking-study-with-new-key-insights-on-how-job-seekers-can-improve-their-resumes-300744217.html

The Ladders timing claim is retained only as historical support for “brief initial scan”; it must not be promoted into a deterministic or universal rule.

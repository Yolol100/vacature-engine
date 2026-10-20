# Career presentation evidence handoff

Last reviewed: 2026-10-20.

This document preserves useful caller-owned CV and portfolio presentation guidance from PR #67 without moving language, candidate claims, CV generation, project metrics, visual design or decisions into the deterministic `vacature-engine`. The live Vacature Register and exact employer instructions remain authoritative.

## Ownership and boundary

- `vacature-search`: verified candidate evidence, CV tailoring, recruiter/application guidance, portfolio and case-study relevance.
- Design/commercial owner: visual design and conversion when the portfolio also serves prospective clients.
- `vacature-engine`: deterministic vacancy eligibility, ranking helpers, verified handoff plumbing and artifact provenance, **not** CV or portfolio content creation.
- Require active, verifiable claim provenance. Never change official job titles, fabricate skill levels, infer work metrics, or attribute an employer/team outcome to a candidate without evidence.

## Bounded presentation guidance

1. Make the CV concise and easy to scan. A brief initial recruiter scan is a useful design heuristic, not a universal '6 seconds' or '7.4 seconds' law.
2. Preserve official historical job titles; use a functional clarification only if it is factually equivalent and directly evidenced. Align terminology with the vacancy only when truthful.
3. Favor clear role-specific evidence over repeated skill/value slogans. Keep parser-critical information in readable body text, not decorative columns, graphics, headers or text boxes.
4. A portfolio case should explain context, candidate's own contribution, relevant tools, decisions, process evidence, delivered output and a verified result or learning. Do not imply a measured improvement when none was measured.
5. Evidence-bearing visuals (captioned shipped pages, verified before/after work, sketches/flows, accessible QA, performance checks or relevant source code) are more useful than unlabelled decorative mockups.
6. A shared evidence-backed case can have different recruiter and client-facing summaries and calls to action without changing the underlying facts.
7. Do not move named projects, cases or repositories into the CV when the current caller-owned pack policy excludes them. Up to three verified, role-relevant work-sample links may be added to a motivation only when useful and allowed; employer requirements take precedence.
8. No claim about Dutch/English fluency or CEFR proficiency is supported by merely specifying the language in which a CV was written.

## Source context (guidance, not runtime requirements)

- Harvard FAS MCS (2026), [Resumes for Industry](https://careerservices.fas.harvard.edu/blog/2026/09/15/resumes-for-industry-grad-student-edition-2026/): tailored, factual skills and project/action/result framing.
- Nielsen Norman Group (2019), [5 Steps to Creating a UX-Design Portfolio](https://www.nngroup.com/articles/ux-design-portfolios/): context, process, ownership and clear audience.
- Greenhouse Support (2026), [Unsuccessful resume parse](https://support.greenhouse.io/hc/en-us/articles/200989175-Unsuccessful-resume-parse): CV parser and format limitations.
- See [Application pack best practices](APPLICATION-PACK-BEST-PRACTICES.md) for the current delivery, language, filename and employer-rule defaults.

The historical recruiter eye-tracking studies cited in PR #67 are not binding or deterministic evidence. This handoff must never admit an unverified role or produce a score.

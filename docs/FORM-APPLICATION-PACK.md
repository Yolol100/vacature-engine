# Form application pack boundary

`vacature-search` may prepare a read-only application pack when a canonically verified vacancy uses an official employer/ATS form. This remains caller-owned behavior: `vacature-engine` does not browse forms, answer candidate questions, store personal application data, generate CV prose, create accounts, bypass CAPTCHA, or submit applications.

## Output contract

For each form-based vacancy, the caller prepares:

1. **Vacancy name** — exact role title + employer.
2. **Answers to the questions** — in official form order, evidence-bound and ready for the user to review/fill.
3. **CV** — vacancy-specific, based on the canonical CV and delivered in the application site's requested format.

Only the official canonical employer/ATS form may be used as the question source. Hidden or inaccessible questions must never be guessed.

## Answer classes

- `verified_factual`: direct from verified candidate evidence or explicit current user input.
- `approved_reuse`: only from a user-approved `ApplicationAnswers` entry for an exact or semantically equivalent question.
- `evidence_bound_draft`: a new concise draft for motivation/experience, using verified candidate facts only.
- `user_confirmation_required`: salary, current availability/start date, work authorization/legal declarations, relocation, sensitive/personal data, or other current-state answers that require human confirmation.
- `manual_assessment`: coding/writing tests, take-home assessments, quizzes, or questions where the employer explicitly prohibits AI-generated answers or requires the candidate's own response.

A vacancy requirement is never candidate evidence. The caller must not invent claims, dates, salary, legal status, or experience.

## Safety and submission boundary

- Inspect public official forms read-only.
- Do not bypass login, CAPTCHA, verification, or restricted steps.
- Do not auto-submit or click final application confirmation.
- Follow explicit employer AI-disclosure/prohibition instructions.
- A prepared pack is not an application submission. `submitted`/`applied` requires real provider evidence or explicit user confirmation.

## CV boundary

Vacancy-specific CV tailoring stays in `vacature-search`. The engine may only support deterministic CV artifact metadata already covered by the CV Artifact Contract. It never writes semantic CV content.

## Runtime ownership

The live `Vacature Register` owns feature switches, source/evidence registry, application state, approved reusable answers, and lifecycle evidence. The Skill owns form interpretation, answer drafting, evidence checks, user-confirmation blockers, and final pack presentation.

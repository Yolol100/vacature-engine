# Form application pack boundary

`vacature-search` may prepare a read-only application pack when a canonically verified vacancy uses an official employer/ATS form. This remains caller-owned behavior: `vacature-engine` does not browse forms, answer candidate questions, store personal application data, generate CV prose, create accounts, bypass CAPTCHA, accept consent, sign attestations, or submit applications.

## Output contract

For each form-based vacancy, the caller prepares:

1. **Vacancy name** - exact role title + employer.
2. **Answers to the questions** - in official form order, evidence-bound and ready for the user to review/fill.
3. **CV** - vacancy-specific, based on the canonical CV and delivered in the supported/preferred application format.

Only the official canonical employer/ATS form may be used as the question source. Hidden or inaccessible questions must never be guessed.

## Field metadata

For every visible field, the caller should preserve the information that changes how the answer must be entered:

- exact question/label and visible help text;
- required vs optional;
- answer type;
- allowed options;
- visible character/word/date/number constraints;
- upload type/size/name/count requirements.

Structured fields must be answered in the accepted structure. A yes/no or select option should not be paraphrased into prose, a numeric field should not receive free text, and visible limits must be respected.

## Answer classes

- `verified_factual`: direct from verified candidate evidence or explicit current user input.
- `approved_reuse`: only from a user-approved `ApplicationAnswers` entry for an exact or semantically equivalent question.
- `evidence_bound_draft`: a new concise draft for motivation/experience, using verified candidate facts only.
- `user_confirmation_required`: salary, current availability/start date, work authorization/legal declarations, relocation, or other current-state decisions.
- `user_action_only`: privacy/GDPR acknowledgement, e-signature/attestation, CAPTCHA, voluntary demographic/EEO questions, or sensitive choices the user must make personally. Protected characteristics are never inferred.
- `manual_assessment`: coding/writing tests, take-home assessments, quizzes, or questions where the employer explicitly prohibits AI-generated answers or requires the candidate's own response.

A vacancy requirement is never candidate evidence. The caller must not invent claims, dates, salary, legal status, eligibility, or experience. Core screening fields such as work authorization, location eligibility, required certification and availability require especially strict evidence because application systems can use answers for screening.

## CV / attachments

Format priority is:

1. explicit employer/application-site requirement;
2. official provider-documented preference when the concrete flow supports it;
3. configured fallback.

Never upload a rejected file type. Keep the final CV readable and parser-friendly; do not use hidden text, keyword stuffing or other parsing tricks. Required extra attachments must be present or readiness is blocked.

## Safety and submission boundary

- Inspect official forms read-only.
- Do not bypass login, CAPTCHA, verification, or restricted steps.
- Do not auto-submit, click final confirmation, accept consent, or sign an attestation.
- Follow explicit employer AI-disclosure/prohibition/original-work instructions before drafting application prose.
- A prepared pack is not an application submission. `submitted`/`applied` requires real provider evidence or explicit user confirmation.

## Readiness QA

A pack is only ready when every visible required field is accounted for with a valid answer or an explicit user/manual-action marker; structured answers fit their field type/options/limits; all required files follow naming/format instructions; employer AI/original-work rules were checked; spelling/links were reviewed; and no final application action was taken.

## Runtime ownership

The live `Vacature Register` owns feature switches, source/evidence registry, application state, approved reusable answers, and lifecycle evidence. The Skill owns form interpretation, field-constraint handling, answer drafting, evidence checks, user-action blockers, CV preparation and final pack presentation.

See `docs/APPLICATION-PACK-BEST-PRACTICES.md` for the online evidence used to validate these defaults.
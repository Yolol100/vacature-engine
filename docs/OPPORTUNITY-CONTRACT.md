# Opportunity contract v1.0

`assess_opportunity()` returns an **advisory** score from 0 to 100 for
an already-reviewed vacancy. It is independent of eligibility,
candidate fit, salary preferences, the primary match score and
existing ranking/tie-break rules.

## Inputs

Every input requires explicit supporting evidence:

- `age_hours`: verified employer-posting age, when available. An
  observed/first-seen age may be used by the caller only if provenance
  clearly labels it as **observation freshness**, never as the
  original employer publication date.
- `route_type`: `employer`, `ats`, `job_board` or `other`,
  assigned after canonical-route verification.
- `applicant_count`: only an explicit visible applicant signal;
  unknown remains `None`.
- `deadline_hours`: only an explicitly valid deadline;
  unknown remains `None`.
- `canonical_verified`: `True` only after the employer/ATS
  identity and live role page have been verified.

## Points

- Freshness: up to 35
- Direct route quality: up to 25
- Explicit competition signals: up to 20
- Explicit deadline: up to 10
- Canonical verification: up to 10

Missing freshness, applicant count and deadline receive conservative
neutral points with explicit warnings. The engine never invents inputs.

## Boundaries

The opportunity score:

- Can never override an eligibility hard gate.
- Never modifies `core_fit`, `evidence_fit`, `workstyle_fit`
  or the primary match score.
- Does not affect existing vacancy ranking.
- Is not a prediction of hiring probability.
- Must not authorize automated applications.
- Is a secondary explanatory priority signal for already eligible jobs.

Changes require dedicated contract and evaluation cases; any change
to the primary match score remains governed by the separate ranking
benchmark.

# Vacature Engine — On-Demand Vacancy Search

This repository supports **explicitly requested job searches** through the
`vacature-search` and `webactueel-workflow` skills. It does **not**
automatically submit applications, send messages, or change application states.

## Authoritative sources

- [Vacature Register](https://docs.google.com/spreadsheets/d/1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0/edit)
  - `Config`: live selection rules and thresholds
  - `Bronnen`: the sole source registry; only `active` entries may be queried
  - `Vacatures`, `Applications`, `ApplicationEvents`, `Feedback`,
    `CandidateEvidence` and `JobSnapshots`: identity, prior applications,
    recorded rejections and verified experience
- [Vacature Radar – Nieuwe Vacatures](https://docs.google.com/spreadsheets/d/1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ/edit)
  - Existing `Nieuwe vacatures` sheet is an optional view, **not** a second
    authoritative registry.

## Workflow for a user-requested search

1. Read the live policy, active sources, prior vacancies/applications and
   `Feedback` before ranking or reintroducing any role.
2. Search official employer/ATS pages first. Use permitted public feeds,
   WordPress sources and fresh web discovery as supplementary inputs.
3. Verify on the *official role page* that the opening is current, actually
   published within the configured window (normally seven days), fully remote
   and workable from the Netherlands. Search-index, first-seen and update
   timestamps are **not** employer publication dates.
4. Deduplicate on canonical role URLs and stable provider job IDs against
   current and prior application/`Feedback` evidence. Never recommend a previously
   submitted or rejected role as new.
5. Require verified employer legitimacy, permitted Dutch/English language
   and candidate fit supported by `CandidateEvidence`. Present only verified
   matches, with their exact role URL, publication date and rationale.

Example: “Find new suitable remote jobs posted within the last seven days.”

## Maintained components

- `src/vacature_engine/`: deterministic canonicalization, gates,
  ranking and optional CV metadata. The `vacature-engine` does not generate CV or motivation prose and does not infer candidate experience.
- `ingestion/`: bounded, read-only public ATS/feed adapters and a
  supplementary Google discovery adapter. Static `source-specs.*` files are
  **examples**, not authority to activate a source.
- `tests/` and `ingestion/tests/`: deterministic regression suites.
- `.github/workflows/ingestion-tests.yml`: offline tests only.
- GitHub Actions runs **offline CI/regression tests only**. There are no
  scheduled or manually triggerable GitHub vacancy searches.
- `ingestion/source-specs.deploy.json` and
  `ingestion/source-specs.google-optional.json` are technical adapter examples;
  neither activates a source. Only live `Vacature Register:Bronnen` does.
- On explicit user requests, ChatGPT `vacature-search` reads the live
  `Config` and active sources, performs discovery and specialist validation,
  then delegates deterministic selection to `vacature-engine`.
- Public observations are **unverified** until the exact official employer/ATS
  role, original publication date, remote-NL execution, language, authenticity
  and CandidateEvidence have been checked. No code or GitHub workflow
  automatically submits or changes application status.

## Verified ranking and bounded expansion

A requested run can inspect up to **20 existing active sources in batches of
8 → 8 → 4**. It evaluates cumulative results after each batch and stops when
the live verified-output target is met. Unverified candidates do not stop
expansion. Each source instance is processed once per run, with the adapter's
existing bounded pagination and retries. Official role checks are cached;
the official-page budget remains ten roles.

Known unsafe Arbeitnow links are quarantined per record. Safe results remain
available, and an incomplete feed cannot mark existing vacancies missing or
closed. Other adapter failures retain their existing fail-closed behavior.

Reports include a bounded `source_attempts` audit trail with actual attempt
times, result counts and safe failure categories. The owning workflow can use
it for authorized Register health updates. Total source failure still exits
with code 2 and writes a blocked report; private claims and raw error messages
are excluded from this audit trail.

`Feedback`, `ApplicationEvents`, `Applications`, `Vacatures` and linked
`JobSnapshots` participate in history checks. Provider IDs include the ATS
tenant, so an ID used by two employers cannot merge their vacancies.
Nonproduction records are excluded before canonicalization.

The expanded requirement review covers mandatory and optional skills,
experience years, languages, projects, responsibilities and work style.
It is an aid to specialist review, never an inferred match score.

Use `--verified-assessments /private/assessments.json` only after
`vacature-search` has completed the documented
[verified ranking handoff](docs/VERIFIED-RANKING-HANDOFF.md).
The handoff is tied to the current policy, CandidateEvidence, exact role and
visible official page. Changed inputs, unavailable evidence, unknown mandatory
requirements, missing original dates or unsupported anchors return to review.
Only complete verified inputs reach `top_vacancies`; existing score anchors,
thresholds, weights and ordering are unchanged. Public output contains the
score components and proof digests, not private CandidateEvidence claims/IDs.

GitHub Actions are CI-only; public discovery and private specialist review are
started exclusively by explicit ChatGPT vacancy-search requests. A caller using the Python API can retain the
observations and page cache, review them and call `evaluate_observations` again
within the same current evidence session. Never commit these private inputs or
upload them as public workflow artifacts. A local run may use Python 3.13 when
an HTTP proxy requires HTTP/1.1 CONNECT; Python 3.11 and 3.13 remain regression
targets. CI also runs the actual Python 3.12 suite under the existing protected
branch's required check name; repository protection is unchanged.

Google discovery is optional. It requires a verified free SerpApi account
and active `google-jobs` registration, uses no paid plan, and returns
**unverified discovery candidates only**. See
[the English setup guide](ingestion/docs/FREE-GOOGLE-DISCOVERY.md).

## Ownership and safety

CV and portfolio presentation remain caller-owned. See the [career-presentation evidence handoff](docs/CAREER-PRESENTATION-HANDOFF.md); the engine does not generate claims, assess portfolio design or change vacancy scores from this guidance.

`webactueel-workflow` coordinates multi-step work. `vacature-search`
owns semantic verification, suitability and application drafts. The live
Vacature Register owns mutable search and application policies. The engine
must not become a scheduler, policy owner or second application database.

No automatic submissions, mailbox changes, source activation, or application
status changes. Follow the source registry and the security contract in
[AGENTS.md](AGENTS.md).

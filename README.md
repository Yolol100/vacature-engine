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
- `.github/workflows/free-google-discovery.yml`: optional **manually
  initiated**, quota-controlled discovery. No cron or recurring job.
- `.github/workflows/one-pass-vacancy-review.yml`: optional **manual** one-pass
  research preflight. Reads live Config, Bronnen and application/feedback
  history; uses Google only after a zero-cost Free Plan check and continues
  through the existing Register-active public ATS/API/feed adapters if
  Google is unavailable, paid, or out of free quota. Output is an
  **unverified review queue**, not a ranked/verified shortlist. Exact official
  role status, Netherlands-remote permission, language and CandidateEvidence
  fit still require specialist verification before displaying a recommendation.
  It does not write to the Register or send applications.

Google discovery is optional. It requires a verified free SerpApi account
and active `google-jobs` registration, uses no paid plan, and returns
**unverified discovery candidates only**. See
[the English setup guide](ingestion/docs/FREE-GOOGLE-DISCOVERY.md).

## Ownership and safety

`webactueel-workflow` coordinates multi-step work. `vacature-search`
owns semantic verification, suitability and application drafts. The live
Vacature Register owns mutable search and application policies. The engine
must not become a scheduler, policy owner or second application database.

No automatic submissions, mailbox changes, source activation, or application
status changes. Follow the source registry and the security contract in
[AGENTS.md](AGENTS.md).

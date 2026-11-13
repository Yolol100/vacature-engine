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
- `src/vacature_engine/mail_artifacts.py`: optional **read-only** integrity check for locally prepared, unsent `.eml` drafts. Given the latest approved CV bytes, expected attachment filename and optional recipient/subject, `verify_unsent_eml_cv` checks that exactly one DOCX attachment matches byte-for-byte (SHA-256). Re-run after **every CV edit** before offering the mail draft. This check does not create/send mail, verify skills/claims, or change application status. Never commit private CV or email contents; use synthetic fixtures only.
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

## Performance and safety

- The authorized live `Vacature Register` is now fetched via **one** Google
  Sheets read-only `values:batchGet` call, instead of 7–8 sequential tab
  requests. Public discovery explicitly omits private `CandidateEvidence`.
  Missing or misordered tab results still stop the run before discovery.
- The code runs no scheduled job searches or applications. Concurrent reads
  are limited to avoid provider rate limits. No source, application history
  or mandatory vacancy verification gate is removed.
- CI tests assert overlapping public fetches, sequential SQLite writes,
  deterministic source order, private evidence exclusion and failed provider
  isolation. Relative time savings depend on actual API latency.

## Verified ranking and bounded expansion

The default requested run inspects up to **20 existing active adapter sources
in batches of 8 → 8 → 4** and may stop when the verified-output target is met.
When live Register `vacancy_search_mode=exhaustive_all_active_sources` and
`vacancy_search_stop_when_target_verified=FALSE`, an explicitly requested
non-check run instead attempts **every active registered source**:

- The registered `wordpress-jobs` source now has dedicated, bounded
  **official WordPress Jobs RSS** discovery for the Development and Design
  categories. This reads curated feed items rather than only the homepage,
  but the RSS date is *not* employer-original posting proof, and `Remote`
  or work-from-Netherlands permission is never inferred from the feed.
  Exact employer/ATS, original date and candidate evidence must still be
  verified separately. Feed failures cannot mark roles absent or closed.
- All Register-approved configured ATS/feed adapter instances run in bounded
  batches of up to 8, with no early stop at the output target. Each instance
  is attempted once even on failure; existing per-adapter caps/retries remain.
  Exhaustive mode fetches up to **three independent ATS/feed sources at once**,
  then writes observations and handles deduplication **sequentially on one
  SQLite thread**. This avoids unsafe concurrent database access, duplicate
  requests and changing the source order. Default mode remains sequential.
- Registered sources without adapters get one limited, redirect-disabled public
  landing-page HTML read. Up to 25 visible, role-specific WordPress/WooCommerce
  links may be collected for **unverified** specialist review; sources without
  readable HTML or matching visible links retain explicit statuses. This is
  **not** a full site search, employer authenticity check or verified listing.
  JavaScript-only listings, search pages, multi-page boards, blocked/logged-in
  content and vacancies beyond the first HTML page may not be visible.
  No CAPTCHA/robots/login bypass or bulk page crawling is performed.
- Free Google search still requires the existing account/quota gate. Without
  authorization, its registered public page can be checked for reachability
  only; no paid searches are initiated.
- The report records a per-source attempt ledger,
  `source_visit_summary.all_active_sources_attempted` and
  `public_job_links_discovered_unverified`. Adapter ingestion, unverified
  public HTML link discovery, plain reachability and verified matches remain
  separate. An empty HTML link pass is **not** zero-vacancy proof.
- Final recommendations still require the independent official-page and
  candidate evidence gates. Official-role checks are cached. Normal mode
  retains its **10-role** safety budget; exhaustive mode can use explicit,
  bounded live Register limits without relaxing any evidence gate.
  A full source-attempt audit must not be mistaken for exhaustive vacancy
  verification.

### Optional exhaustive verification limits (live Config)

- `vacancy_exhaustive_review_candidate_budget`: maximum candidates screened
  after full discovery (1–500; absent = existing normal cap).
- `vacancy_exhaustive_official_page_budget`: maximum unique official ATS job
  pages checked for date/remote/NL/form evidence (1–100; absent = 10).
- `vacancy_exhaustive_return_all_verified`: `TRUE` returns **all actually
  verified matches within the above review/official budgets**, rather than
  using the normal `max_output_roles` display cap. Unverified roles remain
  pending and cannot become CV-ready recommendations.
- Reports now expose the configured review/official budgets, number exceeding
  the candidate review budget and how many verified matches were ranked.
- Exhaustive official ATS page evidence uses at most three concurrent reads,
  retaining the same strict page budget, original candidate order, exact URL
  cache, no login/redirect access and all existing eligibility gates. This
  reduces waiting, but a successful test is not proof of real-world vacancy
  coverage.
  Exceeding a budget is *incomplete coverage*, not proof of no jobs.
- These are on-demand limits, not a recurring search. Official role pages
  can be slow or inaccessible; external ATS, search results and country/age
  restrictions still determine real completeness. The specialist skill, not
  this deterministic engine, produces per-role CVs and motivation text.

The `check` mode remains completely offline/read-only: it plans and reports
source coverage without making website requests.

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

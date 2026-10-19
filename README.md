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
  Google is unavailable, paid, or out of free quota. Sources follow the
  live Register's discovery-class/high-source priorities and then the
  curated tenant order in `source-specs.deploy.json`, rather than
  alphabetical employer names. Retired sources remain disabled.
  The default output is an **unverified review queue**. An explicitly supplied,
  current specialist evidence handoff can now produce final recommendations
  through the existing ranking engine. Exact official
  role status, Netherlands-remote permission, language and CandidateEvidence
  fit still require specialist verification before displaying a recommendation.
  It does not write to the Register or send applications.
  The official-check stage now recognizes only current, Register-approved ATS
  observations as official evidence; it flags country restrictions, remote
  status, declared language and active CandidateEvidence support. Direct
  source restrictions and expired listings can remove obviously unsuitable
  records before review. Search results and job boards **cannot verify
  themselves**. Missing employer proof, Netherlands hiring eligibility,
  application language or semantic fit remains `unverified_review_only`.
  The canonical `vacature_engine.simple.top_vacancies` function is the only
  final ranking authority after all hard gates and fit anchors are grounded;
  missing evidence must never be converted into invented scores.
  The evidence-match preflight now examines **explicit technical requirements**
  from trusted ATS descriptions and compares them with **active, source-backed
  CandidateEvidence**. It reports counts for mapped, unproven and ambiguous
  requirements, never raw personal claims or evidence IDs. Optional skills,
  marketing copy, unverified language or experience requirements cannot
  become invented fit. The existing validated 30-case ranking benchmark and
  score anchors are unchanged; even full mapped skill coverage is **not**
  a final ranked recommendation until the official job route, candidate
  eligibility, full semantic fit and scoring anchor evidence are established.
  The tenant-bound official-page checker also requires the exact job title
  to appear in visible page content alongside matching first-party JobPosting
  markup. A matching JSON-LD script alone is not sufficient.
  ATS job descriptions can be flattened by upstream normalization. The
  requirement comparison therefore recovers only explicitly marked sections
  such as `Requirements:` and `Benefits:`; it never treats benefits or
  negative CandidateEvidence claims as required-skill proof.
  ATS `published_at` can mean the **last** publication, not the original
  posting date; recently republished roles remain unverified until an
  original employer date is confirmed. An application page's `<html lang>`
  reports interface language only, not which language applications may use.
  A 200 OK response from the exact ATS application route is not enough to
  confirm a usable form: the read-only checker also looks for a visible form
  with email and submit controls. Client-side or inaccessible forms stay
  unknown rather than being marked suitable.
  The review output lists missing official, remote/NL, language and skill-fit
  evidence; it suppresses only definitive official 404/410, expired
  `validThrough`, and first-party original posting dates outside live
  policy. Missing information is not a rejection or a match score.
  Every discovery observation must originate from an active Register source
  before it can enter review. Existing third-party boards/feeds are
  negative-only geographic filters: explicit Philippines/LATAM-only locations
  and exclusive foreign residency statements are withheld from the NL
  review queue, but never used as positive proof of NL eligibility or to
  change a vacancy/application lifecycle state. A stale board publication
  timestamp adds only a `discovery_date_older_than_policy` review alert:
  the original employer posting date remains unknown. These limits prevent
  expired or region-restricted board listings from being mistaken for newly
  verified job recommendations, even when Google search quota is exhausted.

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

The manual GitHub workflow remains discovery/review-only because it has no
private specialist handoff. A caller using the Python API can retain the
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

`webactueel-workflow` coordinates multi-step work. `vacature-search`
owns semantic verification, suitability and application drafts. The live
Vacature Register owns mutable search and application policies. The engine
must not become a scheduler, policy owner or second application database.

No automatic submissions, mailbox changes, source activation, or application
status changes. Follow the source registry and the security contract in
[AGENTS.md](AGENTS.md).

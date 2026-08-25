# vacature-engine

Credential-free helper library for the `vacature-search` ChatGPT Skill.

The Skill remains the control plane. This repository only owns deterministic code, public-source adapters and tests. If GitHub or this package is unavailable, the Skill must still be able to run with its bundled fallback helpers.

## What it owns

- URL/title/employer normalization, stable vacancy IDs and content hashes
- deterministic hard gates, scoring and application-readiness guard
- generic worldwide work-eligibility aliases with legacy Netherlands-key compatibility
- one normalized `JobRecord` schema
- credential-free public-read adapters for Greenhouse, Lever, Ashby, SmartRecruiters and Personio XML
- shared HTTP retries/backoff/error mapping without proxy rotation or access-control bypass
- bounded parallel source fetching with deterministic source order, same-source/semantic deduplication and finite recency helpers
- official `JobPosting` JSON-LD evidence extraction with explicit remote/location/date signals
- optional public catalog search through `ats-scrapers` (no account/API key)
- optional Trafilatura extraction and Playwright rendering for normal public pages
- CI, Dependabot and regression/parity vectors

## What it never owns

Profile truth, CV files, Google Drive history, Outlook credentials, application sending, CAPTCHA solving, login automation, proxy rotation, VPN/TLS impersonation, employer contact or application submission.

## Install

Core install has no runtime dependencies:

```bash
python -m pip install -e .
```

Optional extras:

```bash
python -m pip install -e '.[extract]'   # Trafilatura
python -m pip install -e '.[browser]'   # Playwright public rendering
python -m pip install -e '.[catalog]'   # ats-scrapers public hosted dataset
python -m pip install -e '.[dev]'       # Ruff
```

Playwright additionally needs a browser binary:

```bash
python -m playwright install chromium
```

## CLI

```bash
vacature-engine adapters
vacature-engine id --employer Acme --title 'Senior WordPress Engineer' --url 'https://example.com/jobs/1?utm_source=x'
vacature-engine hash --text 'vacancy description'
vacature-engine gate --json gate.json
vacature-engine score --json score.json
vacature-engine application --json application.json
vacature-engine fetch --source ashby --slug openai --days-back 7
vacature-engine fetch --source lever --slug example --option region=eu
vacature-engine batch --json sources.json --max-workers 4
vacature-engine catalog --json catalog-search.json
vacature-engine structured --file vacancy.html
```

All commands emit JSON to stdout. Errors are JSON on stderr and return exit code 2.

## Recommended execution

Do not use this repository as the orchestrator. The reliable order is:

1. The ChatGPT Skill reads Drive state and discovers worldwide remote candidates across multiple source lanes.
2. Use this repo only for deterministic normalization, adapters, dedupe, gates and score arithmetic.
3. Reopen serious candidates at the best available live listing and independently verify freshness, fully-remote scope, work/location eligibility and active status; recover employer/original ATS evidence only for missing, conflicting or suspicious facts or to recover an application route.
4. A `plausible` work-eligibility state can remain visible during search, but application preparation requires explicit eligibility confirmation for the actual employee/contractor arrangement and a passed legitimacy check.
5. Only after those semantic checks pass, prepare an application package; Outlook remains draft-only.
6. Persist results to Drive and read them back.

For maintenance/release checks run:

```bash
python -m pip install -e '.[dev]'
python scripts/release_check.py --require-ruff
```

The release check verifies required files, full-SHA Action pins, least-privilege CI, compilation, unit/regression tests, the adversarial/metamorphic scenario audit and Ruff. Runtime vacancy correctness still requires live evidence from the selected listing; a complete established job-board listing may prove visible facts, while employer/original evidence is used to resolve conflicts or missing application routes. A green build is not proof that a vacancy passes the hard gates.

## Eligibility compatibility

Preferred policy inputs are `work_eligibility` and `work_eligibility_certainty`. Legacy `netherlands_eligibility` and `netherlands_certainty` remain accepted for compatibility with older vectors and Drive data. `geographic_restriction_blocks` is the generic incompatible-location flag; `us_residents_only` remains accepted as a legacy specific blocker.

The application guard also requires `work_eligibility_confirmed=true` and `legitimacy_check_pass=true`. These conditions apply to both email and no-email/manual-form preparation.

## Adapter policy

Adapters only call public employer/ATS endpoints. A 401/403/406 is classified as blocked and stops; it is never retried through proxies, stealth browsers or alternate identities. 408/429/selected 5xx responses receive at most one bounded retry. HTTPS redirects may not downgrade to HTTP. Redirects away from the expected ATS host are rejected so an invalid company slug cannot silently become a marketing page.

`posted_at=None` is intentional when an adapter does not expose a trustworthy source timestamp. The Skill may still use a clearly displayed <=7-day date/age from a live established job-board listing, recording its semantics as listing freshness; conflicting older employer/original evidence must be handled conservatively.

## Supported public-read adapters

| Adapter | Public route | Important limitation |
| --- | --- | --- |
| Greenhouse | Job Board GET API | Prefer `first_published` for original age; never substitute `updated_at` |
| Lever | Postings API | Creation timestamp is distinct from update time; supports global and EU hosts |
| Ashby | Public Job Postings API | `publishedAt` is last-published evidence, not automatically original |
| SmartRecruiters | Posting API public-posting route | Paginated; `releasedDate` stays discovery-only unless original-age semantics are proven |
| Personio | Public careers XML feed | Uses current `*.jobs.personio.com/xml` and direct `/job/{id}` URLs; publication age may remain unknown |

Workable and Teamtailor are not implemented as keyless API adapters because their official APIs require credentials. Recruitee's careers API is intentionally not made a long-term dependency because Recruitee has announced authentication will become mandatory on 10 February 2027.

## Optional public catalog

The `catalog` extra integrates only the base `ats-scrapers` hosted-dataset search. It does not enable that project's scraper/stealth extras. This provides broad discovery without an API key or account. A candidate still needs a complete live listing before hard-gate use; employer/original verification is only mandatory when material facts conflict, remain unclear or the application route must be recovered.

## Development

```bash
python -m pip install -e '.[dev]'
python scripts/release_check.py --require-ruff
```

See `docs/ARCHITECTURE.md`, `docs/COMPARABLE_REPOS.md` and `SECURITY.md` for design boundaries and review decisions.

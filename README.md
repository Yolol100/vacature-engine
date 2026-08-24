# vacature-engine

Credential-free helper library for the `vacature-search` ChatGPT Skill.

The Skill remains the control plane. This repository only owns deterministic code, public-source adapters and tests. If GitHub or this package is unavailable, the Skill must still be able to run with its bundled fallback helpers.

## What it owns

- URL/title/employer normalization, stable vacancy IDs and content hashes
- deterministic hard gates, scoring and application draft guard
- one normalized `JobRecord` schema
- credential-free public-read adapters for Greenhouse, Lever, Ashby, SmartRecruiters and Personio XML
- shared HTTP retries/backoff/error mapping without proxy rotation or access-control bypass
- bounded parallel source fetching, deduplication and recency helpers
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
```

All commands emit JSON to stdout. Errors are JSON on stderr and return exit code 2.

## Recommended execution

Do not use this repository as the orchestrator. The reliable order is:

1. The ChatGPT Skill reads Drive state and discovers candidates.
2. Use this repo only for deterministic normalization, adapters, dedupe, gates and score arithmetic.
3. Reopen serious candidates at the official employer/original ATS and independently verify original date, remote scope, Netherlands eligibility and active status.
4. Only after those semantic checks pass, prepare an application package; Outlook remains draft-only.
5. Persist results to Drive and read them back.

For maintenance/release checks run:

```bash
python -m pip install -e '.[dev]'
python scripts/release_check.py --require-ruff
```

The release check verifies required files, full-SHA Action pins, least-privilege CI, compilation, unit/regression tests and Ruff. Runtime vacancy correctness still requires live official evidence; a green build is not proof that a vacancy passes the hard gates.

## Adapter policy

Adapters only call public employer/ATS endpoints. A 401/403/406 is classified as blocked and stops; it is never retried through proxies, stealth browsers or alternate identities. 408/429/selected 5xx responses receive bounded exponential backoff. Redirects away from the expected ATS host are rejected so an invalid company slug cannot silently become a marketing page.

`posted_at=None` is intentional when a source does not expose an original publication timestamp. The Skill must treat that as unknown and fail its <=7-day freshness gate unless another official source proves the original date.

## Supported public-read adapters

| Adapter | Public route | Important limitation |
| --- | --- | --- |
| Greenhouse | Job Board GET API | `updated_at` is not treated as original publish date |
| Lever | Postings API | Supports global and EU hosts |
| Ashby | Public Job Postings API | Uses explicit `isRemote` when available |
| SmartRecruiters | Posting API public-posting route | No credential is configured; if the provider/account requires auth, fail closed and mark the source degraded |
| Personio | Public careers XML feed | Feed jobs still need exact canonical vacancy resolution |

Workable and Teamtailor are not implemented as keyless API adapters because their official APIs require credentials. Recruitee's careers API is intentionally not made a long-term dependency because Recruitee has announced authentication will become mandatory on 10 February 2027.

## Optional public catalog

The `catalog` extra integrates only the base `ats-scrapers` hosted-dataset search. It does not enable that project's scraper/stealth extras. This provides broad discovery without an API key or account; every serious candidate still needs canonical official-source verification by the Skill.

## Development

```bash
python -m pip install -e '.[dev]'
ruff check .
python -m unittest discover -s tests -v
```

See `docs/ARCHITECTURE.md`, `docs/COMPARABLE_REPOS.md` and `SECURITY.md` for design boundaries and review decisions.

# Comparable repository review

Reviewed in August 2026. This repository implements compatible ideas independently; it does not copy third-party source code.

## kalil0321/ats-scrapers

Useful patterns adopted:

- canonical typed job schema across sources;
- adapter registry and small stable adapter interface;
- shared HTTP layer instead of per-source retry code;
- async/concurrency concept translated here to bounded standard-library thread concurrency;
- separate hosted public dataset from scraper runtime;
- live tests separated from deterministic unit tests;
- Ruff/dev-quality configuration.

Not adopted:

- proxy support, TLS impersonation, stealth Chromium and escalation around blocks;
- broad source surface that would make the Skill harder to audit.

## JobSpy

Useful patterns adopted:

- one normalized output shape across discovery sources;
- remote/compensation/date fields represented explicitly;
- source-specific exceptions/failure handling;
- `results_wanted`/recency-style bounded retrieval concept.

Not adopted:

- direct scraping of LinkedIn/Indeed/Glassdoor/ZipRecruiter as a core dependency;
- proxy/VPN recommendations after rate limiting.

Those sites remain discovery sources handled by ChatGPT web search and canonical employer verification.

## job-seek / ATS job scraper projects

Useful patterns adopted:

- configurable source list;
- public ATS-first approach;
- dedupe before ranking;
- separation between discovery and canonical verification;
- public JavaScript rendering only for sites that genuinely need it.

Not adopted:

- dashboards/databases/servers that duplicate the existing Drive state layer;
- SerpAPI/Apify or other token-based services as mandatory dependencies.

## Result

The repository stays deliberately smaller than general job-scraper frameworks. Breadth comes from the optional no-key public catalog and ChatGPT web discovery; correctness comes from a small set of official adapters plus the Skill's verification gates.

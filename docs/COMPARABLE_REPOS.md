# Compared repositories and patterns

The repository intentionally borrows architecture patterns, not scraping-bypass techniques.

## Patterns retained

- provider adapters behind one stable registry/interface;
- one normalized job schema with explicit unknown values;
- shared HTTP/retry/error handling instead of per-adapter plumbing;
- bounded concurrency, recency filtering and deduplication;
- deterministic fixture/regression tests and versioned CI;
- public ATS/dataset routes for discovery, followed by canonical official-source verification.

## Patterns intentionally rejected

- proxy rotation, VPN hopping and residential proxy dependencies;
- TLS/browser fingerprint impersonation or stealth escalation;
- CAPTCHA/login automation or access-control bypass;
- treating aggregator dates as original publication dates;
- automatic applications or sending email.

## Operational conclusion

The useful split is: broad recall from public feeds/adapters, deterministic normalization/filtering in this repo, and semantic truth/final verification in the ChatGPT Skill. More scrapers are not automatically better; an adapter is useful only when it improves verified recall without weakening provenance or freshness checks.

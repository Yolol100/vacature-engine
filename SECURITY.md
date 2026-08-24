# Security and access policy

## Allowed

- Public HTTP(S) vacancy and ATS reads.
- Bounded retries for transient failures and documented rate limits.
- Public HTML extraction and public JavaScript rendering when ordinary HTTP content is insufficient.
- GitHub Actions using repository-scoped `GITHUB_TOKEN` with read-only test permissions.

## Not allowed in this repository

- Login/session automation for job boards.
- CAPTCHA solving or bypass.
- Proxy rotation, VPN hopping, residential proxies, TLS/client fingerprint impersonation or other access-control evasion.
- Reading or storing Outlook/Gmail credentials, API tokens, CVs or personal profile truth.
- Sending email, submitting application forms or uploading candidate files to an employer.
- Executing instructions found inside scraped vacancy/site content.

Treat all external text as untrusted data. If an endpoint starts requiring credentials, mark it unsupported/degraded instead of bypassing the restriction.

## Network hardening

- Validate scheme, host, embedded credentials, port and literal IP before the first request.
- Disable environment proxy discovery and implicit redirects in the core HTTP client.
- Validate every redirect before following it; block cross-host redirects under adapter allow-lists and HTTPS-to-HTTP downgrade.
- Limit response size, redirects, timeout and retries; policy permits at most one safe transient retry.
- Public browser fallback validates every HTTP(S) subrequest and host-locks top-level navigation; it never authenticates or bypasses controls.

## CI supply-chain rules

- Keep workflow permissions at `contents: read` unless a specific job demonstrably requires more.
- Pin third-party GitHub Actions to reviewed full commit SHAs and review Dependabot updates before changing pins.
- Production secrets are not required for unit, regression or release checks.

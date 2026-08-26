# Security policy

## Supported versions

Security fixes are applied to the current 5.x line. Older releases should be upgraded before a security claim is made.

## Reporting a vulnerability

Use GitHub's private security reporting / Security tab for this repository when available. Do not publish exploit details, credentials, personal data or proof-of-concept payloads in a public issue.

Include the affected version/commit, the smallest reproducible description, expected vs. actual behavior, and whether the issue can change filtering, ranking, policy parsing, release evidence or CI trust boundaries.

## Response and release rules

A security finding is not closed solely because a scanner is green. Fixes require a regression test, the relevant CI/security checks, readback of the changed files and a new release note when the public contract changes. Secrets must never be committed to the repository or release artifacts.

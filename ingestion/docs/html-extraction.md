# Accountless HTML extraction

The `jsonld` ingestion adapter uses two local open-source libraries and requires no account, API key or MCP server:

- `extruct==0.18.0` extracts embedded JSON-LD from public HTML.
- `trafilatura==2.2.0` supplies a main-text fallback only when a valid `JobPosting` object has no description.

Boundaries:

- This layer does not discover or rank vacancies by itself.
- A valid Schema.org `JobPosting` object is still required by the `jsonld` adapter.
- Main-page text is discovery evidence only and does not establish remote status, candidate fit, salary eligibility or open/closed status.
- Canonical employer/ATS verification remains required before `vacature-search` accepts or ranks a role.
- Network acquisition continues through the existing bounded HTTP client and active-source registry gates.

# Email application and Outlook draft boundary

Owner: `vacature-search` under `webactueel-workflow`. Live Vacature Register Config and official employer instructions are authoritative. `vacature-engine` never writes emails, connects to mailboxes, drafts or sends.

## Prepare

1. Verify exact official role, recipient, required subject, application language, AI/original-work restrictions and any required attachments. Never guess the recipient or candidate facts.
2. Read `Applications`, `ApplicationEvents`, `CandidateEvidence`, live Config and canonical CV. Reuse the verified canonical CV by default; tailor or create a second language only on explicit request or employer requirement.
3. Default DOCX unless the employer requires PDF. Follow the user's current visible filename (including `CV.docx`), otherwise live Config; keep vacancy-scoped internal artifact identity. Verify real bytes, content, extension and size, not just filename.
4. For a first application, use the official language and two short substantive paragraphs unless employer instructions override. For a previously submitted role, use a concise follow-up asking whether the position is open and whether the candidate remains eligible; no new motivation required.

## Outlook draft: one active draft per vacancy and recipient

1. Use Outlook when selected by live Config. Search existing Outlook drafts and exact recipient/role before creating any new draft. Gmail historical checks are read-only unless separately authorized.
2. When connector supports in-place update/removal, replace the old CV attachment on the existing draft. Otherwise, create a replacement only after checking the original, verify the new draft with exactly one correct CV, then retire the old draft. Never stack multiple active drafts.
3. Read back recipient, subject, body, exact attachment names/count and unsent state. A draft never means submitted. Do not fabricate `draft_created_at` or claim attachment-content verification from a filename alone.
4. Record verified `draft_provider`, `draft_id`, `cv_file_name` and evidence in live Register only after readback. No automatic sending.

## Final QA

Check employer requirements, factual claims, CV content/format, language, exact recipient/subject, one active draft, one correct CV, unsent state, and register readback. If a required connector action or source is unavailable, mark blocked/unknown rather than PASS.

See `docs/MAILBOX-APPLICATION-RECONCILIATION.md` for the read-only mailbox and historical-event boundary.

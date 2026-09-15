# Email application pack boundary

`vacature-search` may prepare an email application pack only when a canonically verified employer or employer-owned ATS vacancy explicitly names email as the official application route. This is caller-owned preparation. `vacature-engine` does not write candidate prose, inspect outbound mail composition, create drafts, attach files, or send email.

## Output contract

For an official email route, the caller prepares these items in this order:

1. **Vacancy name** - exact role title and employer.
2. **Email subject** - use the employer-required subject exactly; when none is specified, use the exact vacancy title plus candidate name according to live Config.
3. **Email content** - a short vacancy-specific motivation letter with a greeting, exactly two compact content paragraphs, and a sign-off.
4. **CV** - the vacancy-specific CV based on the immutable canonical CV.

Employer instructions always override defaults. If a separate cover letter, portfolio, references, question responses, specific filename, or other material is required, prepare it or block readiness rather than silently omit it.

## Recipient and subject rules

- Use only the exact application email address published on the verified canonical vacancy.
- Never infer, guess, construct, or substitute a recipient address.
- Copy an employer-required subject line literally, including any job ID or naming convention.
- Without an employer subject instruction, keep the fallback concise and identifiable: exact vacancy title + candidate name.

## Motivation email rules

- Use the vacancy language.
- Keep exactly two content paragraphs; greeting and sign-off are separate.
- The message should answer why this role/employer and why this candidate without restating the CV.
- Use one or two directly relevant verified experiences.
- Keep the writing personal, human, simple and active; avoid generic application cliches, inflated claims and AI-like phrasing.
- Target roughly 80-130 total words unless the employer or live Config imposes a stricter limit.
- Use only employer/company details verifiable on the official vacancy or official employer site.
- If a separate cover letter attachment is required, keep the email body shorter to avoid duplication.

## AI / original-work instructions

Before application prose is prepared, inspect the official instructions for explicit rules around AI, ChatGPT, generative AI, disclosure, original work, or own words.

- Follow those rules exactly.
- If AI-generated application prose is prohibited, do not produce a ready-made email body; provide factual evidence bullets for the user to write from.
- If disclosure is required, follow the requested disclosure format.

## CV and filename

User-facing delivery policy:

1. Use DOCX by default.
2. Switch to PDF only when the official email instructions explicitly require a PDF attachment or otherwise make PDF mandatory.
3. PDF being supported or generally preferred is not enough to override the DOCX default.
4. If the employer prescribes an exact filename, use it exactly. Otherwise use `Andrew_Baeten_Resume.<ext>` when the official flow calls the document `Resume`; otherwise use `Andrew_Baeten_CV.<ext>`.
5. Do not add employer, role, date, `final`, or version numbers to the default visible filename. Keep vacancy-bound artifact identity/provenance internal.
6. Check extension and any explicit/provider file-size limit before readiness.

Keep the CV reader/ATS friendly: simple one-column structure where practical, standard section headings, no photos/graphics/word art, no core content dependent on tables/text boxes, and no essential contact information only in headers/footers.

## Final QA

A pack is only ready when the exact recipient/route, subject, role/employer/job ID, two-paragraph structure, word limit, factual support, spelling/grammar, attachment name/format/size, required extra materials and AI/original-work rules all pass review. Nothing is sent automatically.

## Draft and submission boundary

If live Config enables an Outlook review draft, the caller may create one only after verification, fit, content, recipient, CV, material and QA gates pass. Draft creation is not submission. The caller must never auto-send. `submitted` or `applied` requires provider evidence or explicit user confirmation.

## Runtime ownership

The live `Vacature Register` owns the email-pack feature switch, subject/body/style rules, recipient policy, draft mode, application status and evidence. The Skill owns route interpretation, evidence-bound writing, CV preparation, QA and user-facing pack presentation.

See `docs/APPLICATION-PACK-BEST-PRACTICES.md` for the online evidence used to validate these defaults.
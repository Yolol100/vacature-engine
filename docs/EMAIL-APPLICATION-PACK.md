# Email application pack boundary

`vacature-search` may prepare an email application pack only when a canonically verified employer or employer-owned ATS vacancy explicitly names email as the official application route. This is caller-owned preparation. `vacature-engine` does not write candidate prose, inspect outbound mail composition, create drafts, attach files, or send email.

## Output contract

For an official email route, the caller prepares these items in this order:

1. **Vacancy name** - exact role title and employer.
2. **Email subject** - use the employer-required subject exactly; when none is specified, use the exact vacancy title plus candidate name according to live Config.
3. **Email content** - a short vacancy-specific motivation letter with a greeting, exactly two content paragraphs, and a sign-off.
4. **CV** - the vacancy-specific CV based on the immutable canonical CV and delivered in the correct supported format.

Employer instructions always override defaults. If a separate cover letter, portfolio, references, question responses, specific filenames, or other materials are required, prepare them or block readiness rather than silently omit them.

## Recipient and subject rules

- Use only the exact application email address published on the verified canonical vacancy.
- Never infer, guess, construct, or substitute a recipient address.
- Copy an employer-required subject line literally, including any job ID or naming convention.
- Without an employer subject instruction, keep the fallback concise and identifiable: exact vacancy title + candidate name.

## Motivation email rules

- Use the vacancy language.
- Keep exactly two content paragraphs; greeting and sign-off are separate.
- The message should answer two questions: why this role/employer, and why this candidate. It should not simply restate the CV.
- Paragraph 1 should open naturally with a concrete role-specific reason and connect it to one or two directly relevant, verified experiences.
- Paragraph 2 should connect the employer's work, product, users, mission, or way of working to the candidate's verified background and may close naturally with interest in speaking further.
- Keep the writing personal, human, concise and active. Avoid generic application cliches, inflated claims, keyword stuffing and AI-like phrasing.
- Target roughly 120-180 total words unless the employer or live Config imposes a stricter limit.
- Use only employer/company details that are verifiable on the official vacancy or official employer site.
- If a separate cover letter attachment is explicitly required, prepare it separately and keep the email body shorter to avoid duplicating the same text.

## AI / original-work instructions

Before application prose is prepared, the caller should inspect the official instructions for explicit rules around AI, ChatGPT, generative AI, disclosure, original work, or own words.

- Follow those rules exactly.
- If AI-generated application prose is prohibited, do not produce a ready-made email body; provide factual evidence bullets for the user to write from.
- If disclosure is required, do not hide AI assistance; follow the requested disclosure format.

## CV and filename

Format priority is:

1. explicit employer/application-site requirement;
2. official provider-documented preference when relevant;
3. PDF for email/manual-review when supported;
4. configured fallback.

Use an employer-required filename exactly. Otherwise use a clear vacancy-bound name such as `Andrew_Baeten_CV_<Employer>_<Role>.<ext>`. Keep the CV reader/ATS friendly and do not use hidden text or keyword-stuffing tricks.

## Final QA

A pack is only ready when the exact recipient/route, subject, role/employer/job ID, two-paragraph structure, word limit, factual support, spelling/grammar, attachment names/formats, required extra materials and AI/original-work rules all pass review. Nothing is sent automatically.

## Draft and submission boundary

If live Config enables an Outlook review draft, the caller may create one only after verification, fit, content, recipient, CV, material and QA gates pass. Draft creation is not submission. The caller must never auto-send. `submitted` or `applied` requires provider evidence or explicit user confirmation.

## Runtime ownership

The live `Vacature Register` owns the email-pack feature switch, subject/body/style rules, recipient policy, draft mode, application status and evidence. The Skill owns route interpretation, evidence-bound writing, CV preparation, QA and user-facing pack presentation.

See `docs/APPLICATION-PACK-BEST-PRACTICES.md` for the online evidence used to validate these defaults.
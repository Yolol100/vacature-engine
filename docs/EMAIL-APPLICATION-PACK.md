# Email application pack boundary

`vacature-search` may prepare an email application pack only when a canonically verified employer or employer-owned ATS vacancy explicitly names email as the official application route. This is caller-owned application preparation. `vacature-engine` does not write candidate prose, inspect mailboxes for outbound composition, create drafts, attach files, or send email.

## Output contract

For an official email application route, the caller prepares these four items in this order:

1. **Vacancy name** - exact role title and employer.
2. **Email subject** - use the employer-required subject exactly; when none is specified, use the exact vacancy title according to live Config.
3. **Email content** - a short vacancy-specific motivation letter with a greeting, exactly two content paragraphs, and a sign-off. It must sound personal and human, use simple language, and be grounded only in verified candidate evidence.
4. **CV** - the vacancy-specific CV based on the immutable canonical CV and delivered in the site-requested format.

## Recipient and route rules

- Use only the exact application email address published on the verified canonical vacancy.
- Never infer, guess, construct, or substitute a recipient address.
- Do not use this pack when the official route is a form, ATS account flow, Easy Apply, or another non-email route.
- If required extra materials cannot be truthfully prepared, return a blocker instead of an application-ready pack.

## Motivation email rules

- Use the vacancy language.
- Keep exactly two content paragraphs; greeting and sign-off are separate.
- Paragraph 1 should naturally connect the candidate's interest in the role to one or two directly relevant, verified experiences.
- Paragraph 2 should connect the employer's work, product, users, mission, or way of working to the candidate's verified background.
- Avoid generic application cliches, inflated claims, keyword stuffing, and AI-like phrasing.
- Respect any configured maximum word count and employer-specific subject/body instructions.
- Follow explicit employer AI-use or disclosure rules. If AI-generated application text is prohibited, do not provide a ready-made email body; provide only factual evidence bullets for the candidate to write from.

## CV boundary

Semantic CV tailoring remains owned by `vacature-search`. `vacature-engine` may only support the existing deterministic CV Artifact Contract metadata. It never writes or rewrites CV content.

## Draft and submission boundary

If live Config enables an Outlook review draft, the caller may create one only after verification, fit, content, recipient, CV, and requirement gates pass. Draft creation is not submission. The caller must never auto-send. `submitted` or `applied` requires provider evidence or explicit user confirmation.

## Runtime ownership

The live `Vacature Register` owns the email-pack feature switch, subject/body/style rules, recipient policy, draft mode, application status, and evidence. The Skill owns route interpretation, evidence-bound writing, CV preparation, QA, and user-facing pack presentation.
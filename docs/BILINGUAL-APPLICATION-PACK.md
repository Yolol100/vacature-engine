# Application pack boundary

This repository does not generate candidate prose. The following is a caller-owned contract for `vacature-search` and the live Vacature Register. The legacy filename is retained to avoid breaking existing references.

## Input

The caller may start from pasted vacancy text or an online-discovered vacancy. Before tailoring, it resolves one canonical vacancy snapshot and follows official employer/ATS application instructions.

## Default output language

Prepare exactly one vacancy-specific CV and one motivation/cover letter in the official vacancy/application language.

- Dutch official vacancy/application flow -> Dutch CV + Dutch motivation.
- English official vacancy/application flow -> English CV + English motivation.
- Create a second language only when the user explicitly asks for it or the employer requires it.
- When a second language is required, both versions must use the same verified evidence map and may not diverge in facts, metrics, ownership, tools, seniority or results.

## CV placement

Keep named projects, cases and repository lists out of the CV. Do not add Selected Projects, Technical Projects, Cases or repo-catalog sections. The CV may carry the stable portfolio link `https://andrewbaeten.nl/category/cases` in contact information.

## Motivation placement

The motivation contains a greeting, exactly two substantive paragraphs, optional 1-3 verified work-sample bullets only when requested/materially useful, the stable portfolio line, and a first-name-only sign-off.

Dutch: `Vriendelijke groet,` then `Andrew`.
English: `Kind regards,` then `Andrew`.

Select work samples from verified CandidateEvidence/canonical portfolio/public portfolio/exact GitHub readback. Never guess a case slug or repository URL. If an exact case URL is not verified, use the portfolio index.

## Writing and evidence

Use plain human language a nontechnical hiring reader can understand. Technical terms are allowed when vacancy-relevant and verified, but are not decoration. No AI/corporate filler, unsupported self-labels, invented skills, metrics, certifications, ownership or outcomes. Memory may locate evidence but is not itself a new-claim source.

Candidate identity is `Andrew Baeten`. Do not output `Baetem`.

Employer AI/original-work rules override the prose default. If AI-generated application prose is prohibited, the caller returns evidence bullets/outline rather than ready-made motivation text. Prepare-only remains mandatory; no auto-submit/send.

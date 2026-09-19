# Application pack best practices — online validation

Last reviewed: 2026-09-19.

This document records external evidence used to validate the caller-owned form/email application-pack defaults. It does not move application policy into `vacature-engine`.

## Sources reviewed

- Harvard FAS Mignone Center for Career Success, 2026 cover-letter guidance: https://careerservices.fas.harvard.edu/blog/2026/08/10/how-to-write-a-cover-letter-that-actually-gets-you-hired-in-2026/
  - Cover letters should explain why this role and why the candidate, avoid generic openings, connect one or two relevant experiences to employer needs, stay concise, and follow job-specific instructions.

- Harvard FAS internship application guidance: https://careerservices.fas.harvard.edu/blog/2026/02/28/12-common-mistakes-students-make-when-applying-for-internships-and-how-to-avoid-them/
  - Explicit employer instructions for file type, file naming and subject lines should be followed exactly.

- Indeed Career Guide, updated 2026: https://www.indeed.com/career-advice/resumes-cover-letters/name-resume-and-cover-letter-files
  - Avoid generic filenames such as `resume.pdf`; include the candidate's professional name and document type. Underscores are an accepted simple separator.

- Greenhouse Recruiting supported candidate uploads: https://support.greenhouse.io/hc/en-us/articles/360052218132-Supported-formats-for-resumes-cover-letters-and-other-candidate-uploads
  - Greenhouse accepts DOC, DOCX, PDF, RTF and TXT candidate uploads.

- Greenhouse Recruiting resume parsing guidance: https://support.greenhouse.io/hc/en-us/articles/200989175-Unsuccessful-resume-parse
  - Complex tables, multi-column layouts, graphics/photos/word art, text boxes, and contact details in headers/footers can reduce parsing quality.

- Workable application uploads: https://help.workable.com/hc/en-us/articles/115012238108-What-types-of-files-can-be-uploaded-on-the-application-form
  - Workable accepts DOC/DOCX/PDF and other common resume formats; resume uploads have a 5 MB size limit.

- Workable structured application fields: https://help.workable.com/hc/en-us/articles/115012903847-Custom-fields-for-candidate-profiles
  - Application flows can use dates, files, dropdowns and multiple-choice fields; answers should preserve the requested structure.

- Employer examples surfaced through university career services show that AI rules vary:
  - AI disclosure required: https://careerservices.fas.harvard.edu/jobs/ai-now-institute-communications-associate/
  - Original/non-AI cover letter required: https://careerservices.upenn.edu/jobs/w-w-norton-company-college-marketing-internship-summer-2026/

- Career-presentation evidence handoff: [CAREER-PRESENTATION-HANDOFF.md](CAREER-PRESENTATION-HANDOFF.md)
  - Adds bounded resume first-scan, job-title integrity and portfolio/project-evidence guidance while keeping all semantics caller-owned.
  - Historical recruiter timing studies support only a brief-initial-scan heuristic, never a universal fixed number of seconds.

## Policy conclusions

- Employer/application instructions outrank defaults.
- Resume/portfolio presentation semantics remain outside the engine; see `CAREER-PRESENTATION-HANDOFF.md` for the validated caller-owned boundary.
- Keep application packs simple and compact.
- Form packs preserve exact question order and field constraints; structured fields are answered in the accepted format, not rewritten as prose.
- Legal, work-authorization, salary, current-state, sensitive, demographic, consent and signature fields are not inferred.
- Email application prose stays short, specific and human, with exactly two compact content paragraphs when that route is used.
- DOCX is the default CV delivery format. Switch to PDF only when the official form/site explicitly requires PDF, accepts only PDF, or official email instructions explicitly require a PDF attachment.
- General PDF advice or provider preference does not override the user's DOCX default when DOCX is accepted.
- If the employer prescribes a filename, follow it exactly. Otherwise use `Andrew_Baeten_Resume.<ext>` when the official flow calls the document Resume; otherwise use `Andrew_Baeten_CV.<ext>`.
- Keep internal vacancy-bound artifact identity/provenance separate from the visible delivery filename. When several application packs are prepared together, use vacancy-scoped internal paths so the same simple visible filename cannot overwrite another CV.
- Keep the CV parser-friendly: simple structure, no decorative graphics, no core content dependent on tables/text boxes or multiple columns, and no essential contact information only in headers/footers.
- Check supported extension and relevant file-size limits before readiness.
- Official AI/disclosure/original-work instructions are checked before drafting prose.
- Final QA covers route/recipient, exact role/employer, required fields/materials, field limits/options, file name/format/size, factual support, spelling and instruction compliance.
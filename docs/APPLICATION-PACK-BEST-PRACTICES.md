# Application pack best practices — online validation

Last reviewed: 2026-09-15.

This document records external evidence used to validate the caller-owned form/email application-pack defaults. It does not move application policy into `vacature-engine`.

## Sources reviewed

- Harvard FAS Mignone Center for Career Success, 2026 cover-letter guidance: https://careerservices.fas.harvard.edu/blog/2026/08/10/how-to-write-a-cover-letter-that-actually-gets-you-hired-in-2026/
  - Cover letters should explain why this role and why the candidate, avoid generic openings, connect one or two relevant experiences to employer needs, stay concise, and follow job-specific instructions. The guide recommends PDF unless the posting asks for another format.

- Harvard FAS resume/cover-letter resources: https://careerservices.fas.harvard.edu/resources/hes-create-impactful-resumes-and-cover-letters/ and https://careerservices.fas.harvard.edu/resources/gsas-masters-resume-cover-letter/
  - Tailor to the exact organization/position and be brief but specific.

- University of Michigan Career Center: https://careercenter.umich.edu/content/cover-letter-resources
  - When applying by email, the email body can serve as the cover letter; use a professional salutation, concise active writing, employer research, error-free text, and avoid cliches.

- Greenhouse Recruiting application questions: https://support.greenhouse.io/hc/en-us/articles/360025222851-Add-a-custom-application-question-to-a-job-post
  - Questions can have descriptions, answer types, privacy settings and required/optional state.

- Greenhouse Recruiting uploads / candidate guidance: https://support.greenhouse.io/hc/en-us/articles/360052218132-Supported-formats-for-resumes-cover-letters-and-other-candidate-uploads and https://support.greenhouse.io/hc/en-us/articles/43418495049499-MyGreenhouse-FAQ-for-Candidates
  - Greenhouse supports common resume formats; current MyGreenhouse candidate guidance says PDF works best and reminds candidates to review parsed data before submission.

- Workable application question types: https://help.workable.com/hc/en-us/articles/115012087467-What-types-of-questions-can-I-add-to-my-application-form
  - Forms may use paragraph, short-answer, yes/no, dropdown, multiple choice, date, number and file-upload controls; some short-answer fields have hard character limits.

- Workable uploads / application form guidance: https://help.workable.com/hc/en-us/articles/115012238108-What-types-of-files-can-be-uploaded-on-the-application-form and https://help.workable.com/hc/en-us/articles/360047859953-Best-Practices-Optimise-Job-Posts
  - Application questions are screening inputs and file-format constraints matter.

- Employer examples surfaced through university career services show that AI rules vary:
  - AI disclosure required: https://careerservices.fas.harvard.edu/jobs/ai-now-institute-communications-associate/
  - Original/non-AI cover letter required: https://careerservices.upenn.edu/jobs/w-w-norton-company-college-marketing-internship-summer-2026/

## Policy conclusions

- Employer/application instructions outrank generic defaults.
- Form packs preserve exact order and the field constraints that affect how the answer is entered.
- Structured fields are answered in accepted format, not rewritten as free prose.
- Legal, work-authorization, salary, current-state, sensitive, demographic, consent and signature fields are not inferred.
- Email application prose should be short, specific and human, explain why the role and why the candidate, and avoid merely repeating the CV.
- Exact employer subject lines and file naming instructions are copied literally; without a subject instruction, use role title + candidate name.
- CV format priority is explicit employer requirement -> official provider preference -> PDF for email/manual review when supported -> configured fallback.
- Official AI/disclosure/original-work instructions are checked before drafting prose.
- Final QA covers route/recipient, exact role/employer, required fields/materials, field limits/options, file names/formats, factual support, spelling and instruction compliance.
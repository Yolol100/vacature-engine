# Mailbox application reconciliation contract v1.0

Status: caller-owned policy contract for `vacature-search`.

`vacature-engine` does not connect to mailboxes and does not own candidate/application state. The live `Vacature Register` remains canonical. This document defines the boundary that `vacature-search` must honor when connected mailbox evidence is available.

## Goal

Before returning a vacancy as new, and when reconciling application lifecycle state, `vacature-search` should compare the live Vacature Register with connected Gmail and Outlook evidence. This reduces resurfacing of roles that were already applied to and captures later employer outcomes.

## Mailbox coverage

When connected and authorized, inspect read-only evidence from:

- Gmail: Inbox, Sent and Spam;
- Outlook: Inbox/Postvak IN, Sent/Verzonden items and Junk/Ongewenste e-mail.

A connector failure is not equivalent to `no evidence`; report the gap and continue conservatively.

## Read-only safety boundary

Mailbox reconciliation may search and read only. It must never, as part of vacancy reconciliation:

- send or draft messages;
- move, archive or delete messages;
- add/remove labels or categories;
- mark messages read/unread;
- mutate mailbox state in any other way.

Store only minimal application/lifecycle metadata needed for deduplication and auditability. Do not copy unrelated or full mailbox content into the register.

## Strong evidence only

A mailbox signal may update application history only when there is strong evidence, such as:

1. explicit user confirmation of submission;
2. a sent application email that identifies the vacancy;
3. an employer/ATS receipt explicitly confirming the application;
4. a role-specific lifecycle message: employer reply, screening, assessment, interview, offer, rejection or withdrawal acknowledgement.

Preferred identity keys, strongest first:

1. exact canonical vacancy/application URL or provider job ID;
2. exact employer plus exact role title;
3. employer plus strong role-specific evidence requiring semantic adjudication.

Employer-name similarity, generic recruiter mail, newsletters, job alerts, marketing and unrelated messages are never sufficient for automatic merging.

If a message predates a newly tracked vacancy and does not prove the exact role, do not attribute it to that vacancy.

## Lifecycle writes

When strong evidence is established:

- keep `Vacatures` and `Applications` synchronized with the canonical application state;
- append an `ApplicationEvents` event instead of rewriting historical events;
- preserve source/provider and timestamp evidence;
- do not downgrade a later proven lifecycle state because a weaker or older message exists.

Candidate-facing dedupe should treat at least these states as previously handled when configured live: `seen`, `shown`, `submitted`, `applied`, `screen`, `interview`, `assessment`, `final`, `offer`, `rejected`, `withdrawn`, `closed`, and `excluded_user_preference`.

## Separation of responsibilities

- `vacature-search`: owns semantic mailbox reconciliation, application-history policy and candidate-facing dedupe.
- Vacature Register: canonical mutable runtime truth for vacancies, applications, events, sources and Config.
- `vacature-engine`: remains a deterministic helper for vacancy observations/filtering/scoring/artifact metadata and does not gain mailbox credentials or email network code.
- `ingestion/`: remains public vacancy-source acquisition only; mailbox evidence is not a discovery source.

This separation prevents personal mailbox data from entering public ingestion or deterministic vacancy-scoring code while still making mailbox evidence part of the end-to-end vacancy workflow.
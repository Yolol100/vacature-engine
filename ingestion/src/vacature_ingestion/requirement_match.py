"""Evidence-bound technical requirement comparison for official ATS descriptions.

This is a conservative REVIEW AID, not a semantic eligibility decision, an
authenticity check or a match-score generator. Never infer candidate skills
from the role, missing evidence, employer snippets, or generic AI mentions.
CandidateEvidence is read in memory; no private claim or evidence ID is exported.
"""
from __future__ import annotations

import re
from typing import Any

# These are literal, unambiguous technical competencies, not invented CV claims.
# Aliases must mean the same skill; adjacent tools must remain distinct.
_SKILLS: dict[str, tuple[str, ...]] = {
    "wordpress": (r"wordpress",),
    "woocommerce": (r"woocommerce",),
    "elementor": (r"elementor",),
    "gutenberg": (r"gutenberg",),
    "acf": (r"acf", r"advanced custom fields"),
    "php": (r"php",),
    "javascript": (r"javascript",),
    "typescript": (r"typescript",),
    "react": (r"react(?:\.js)?",),
    "nextjs": (r"next\.?js",),
    "html": (r"html(?:5)?",),
    "css": (r"css(?:3)?",),
    "mysql": (r"mysql",),
    "python": (r"python",),
    "ruby": (r"ruby",),
    "laravel": (r"laravel",),
    "django": (r"django",),
    "nodejs": (r"node\.?js",),
    "docker": (r"docker",),
    "kubernetes": (r"kubernetes", r"k8s"),
    "rest_apis": (r"rest(?:ful)?[\s-]*apis?",),
    "graphql": (r"graphql",),
    "git": (r"github", r"\bgit\b"),
    "github_actions": (r"github[\s-]*actions",),
    "playwright": (r"playwright",),
    "accessibility": (r"accessibility", r"wcag", r"toegankelijkheid"),
    "technical_seo": (r"technical[\s-]*seo", r"technische[\s-]*seo"),
    "core_web_vitals": (r"core[\s-]*web[\s-]*vitals",),
    "ux_research": (r"user[\s-]*research", r"gebruikersonderzoek"),
    "wireframes": (r"wireframes?",),
    "n8n": (r"n8n",),
    "zapier": (r"zapier",),
    "make_com": (r"make\.com",),
    "figma": (r"figma",),
    "workflow_automation": (r"workflow[\s-]*automation", r"workflow[\s-]*orchestration"),
}
_TAG_PATTERNS = {
    skill: tuple(re.compile(r"(?<![a-z0-9])(?:" + alias + r")(?![a-z0-9])", re.I)
                 for alias in aliases)
    for skill, aliases in _SKILLS.items()
}
_REQUIRED_SECTION = re.compile(
    r"^(?:requirements?|qualifications?|must[\s-]*haves?|what you (?:bring|need)|"
    r"your (?:skills|experience)|minimum (?:requirements|qualifications)|"
    r"required (?:skills|experience)|vereisten|functie[\s-]*eisen|"
    r"wat (?:we|wij) (?:vragen|zoeken)|eisen|ervaring en vaardigheden)\s*:?\s*$",
    re.I,
)
_OTHER_SECTION = re.compile(
    r"^(?:about (?:us|the company|you)|benefits|perks|we offer|"
    r"what (?:we|you) (?:offer|do)|responsibilities|your (?:role|tasks)|"
    r"nice[\s-]*to[\s-]*have|preferred|bonus|over ons|"
    r"taken|verantwoordelijkheden|wat bieden wij)\s*:?\s*$",
    re.I,
)
_REQUIREMENT_CUE = re.compile(
    r"\b(?:must (?:have|know|be)|required|requirement|you (?:have|need)|"
    r"proficien(?:t|cy) (?:in|with)|experience (?:with|in)|"
    r"knowledge (?:of|in)|hands[\s-]*on (?:with|experience)|"
    r"ervaring met|kennis van|vereist|aantoonbare ervaring)\b",
    re.I,
)
_OPTIONAL = re.compile(
    r"\b(?:nice[\s-]*to[\s-]*have|optional|preferred|a plus|bonus|"
    r"not required|not mandatory|do not (?:need|require)|"
    r"no experience (?:required|needed)|niet vereist|niet nodig|"
    r"geen vereiste|pré)\b",
    re.I,
)
# A negative CV claim is never evidence for a positive job requirement.
_NEGATED_CLAIM = re.compile(
    r"\b(?:no experience (?:with|in)|no knowledge of|without experience"
    r"|not familiar with|not proficient (?:in|with)|"
    r"geen ervaring met|geen kennis van|niet bekend met)\b",
    re.I,
)
# ATS adapters normalize description whitespace. Recover ONLY explicit,
# colon-terminated headings; free prose such as 'our requirements are ...'
# must not start a mandatory section.
_INLINE_HEADING = re.compile(
    r"(?<![A-Za-z0-9])(?P<label>Requirements?|Qualifications?|"
    r"Must[ -]haves?|Required (?:skills|experience)|Vereisten|"
    r"Functie[ -]?eisen|Eisen|Benefits|Perks|Responsibilities|"
    r"Nice[ -]to[ -]have|Preferred|Bonus|Over ons|"
    r"Taken|Verantwoordelijkheden)\s*:",
    re.I,
)
_AMBIGUOUS = re.compile(r"\b(?:or|and/or|ofwel)\b|/", re.I)
_NUMERIC_EXPERIENCE = re.compile(
    r"\b\d+\s*\+?\s*(?:years?|yrs?|jaar)\b", re.I
)
_LANGUAGE_REQUIREMENT = re.compile(
    r"\b(?:fluen(?:t|cy)|native|business level|professional proficiency|"
    r"vloeiend|moedertaal|c1|c2|b2)\b.{0,35}\b"
    r"(?:english|dutch|german|french|spanish|nederlands|duits|frans|engels)\b",
    re.I,
)
_ALLOWED_SOURCES = {"canonical_cv", "github", "user_confirmed", "library_portfolio_master"}


def _skill_tags(value: str) -> set[str]:
    return {skill for skill, patterns in _TAG_PATTERNS.items()
            if any(pattern.search(value) for pattern in patterns)}


def has_positive_skill_claim(claim: Any) -> bool:
    """Whether a CV claim can serve as *positive* skill evidence.

    This same gate must be used by detailed skill matching AND broader
    eligibility preflight: negated/portfolio-index statements prove no skill.
    """
    if not isinstance(claim, str) or not claim.strip():
        return False
    lower = claim.casefold()
    if any(phrase in lower for phrase in (
        "available for vacancy", "profile is https://", "portfolio index"
    )):
        return False
    return _NEGATED_CLAIM.search(claim) is None


def _verified_skills(evidence: list[dict[str, str]]) -> set[str]:
    # A portfolio index/GitHub profile URL, standing alone, is not skill proof.
    result: set[str] = set()
    for row in evidence:
        if (row.get("active", "").casefold() != "true"
                or row.get("source_type") not in _ALLOWED_SOURCES
                or row.get("confidence", "").casefold() not in {"high", "medium"}
                or not row.get("evidence_id")):
            continue
        claim = row.get("claim", "")
        if not has_positive_skill_claim(claim):
            continue
        result.update(_skill_tags(claim))
    return result


def _requirement_groups(description: str) -> tuple[list[set[str]], int]:
    """Extract only explicit *mandatory* technical phrases.

    Skill names in company marketing or duty descriptions are ignored.
    Alternatives, years of experience, foreign languages and unknown prose
    are recorded for human review, never treated as proven requirements met.
    """
    groups: list[set[str]] = []
    uncertain = 0
    in_required = False
    # Public ATS normalization often collapses "Requirements:" and
    # "Benefits:" into a single line. Rebuild only explicit boundaries.
    # Never infer missing section headings or scrape employer marketing.
    sections = _INLINE_HEADING.sub(
        lambda m: "\n" + m.group("label") + ":\n", description[:60_000]
    )
    for line in sections.splitlines()[:300]:
        line = " ".join(line.strip().split())
        if not line:
            continue
        if len(line) < 100 and _REQUIRED_SECTION.fullmatch(line):
            in_required = True
            continue
        if len(line) < 100 and _OTHER_SECTION.fullmatch(line):
            in_required = False
            continue
        if len(line) > 900:
            uncertain += 1
            continue
        for clause in re.split(r"(?<=[.!?;])\s+", line):
            if not clause.strip():
                continue
            explicit = in_required or bool(_REQUIREMENT_CUE.search(clause))
            if not explicit or _OPTIONAL.search(clause):
                continue
            tags = _skill_tags(clause)
            if _NUMERIC_EXPERIENCE.search(clause) or _LANGUAGE_REQUIREMENT.search(clause):
                uncertain += 1
            if not tags:
                uncertain += 1
                continue
            if tags and _AMBIGUOUS.search(clause):
                uncertain += 1
                # "WordPress or Drupal" is not proof that both are required.
                continue
            groups.append(tags)
    return groups, uncertain


def compare_requirements(row: dict[str, Any], evidence: list[dict[str, str]]) -> dict[str, Any]:
    """Return aggregate, privacy-safe proof coverage only.

    In particular, **absence from CandidateEvidence is not proof of inability**.
    A positive technical token match is not semantic/core fit, legal work
    eligibility, application language or an authorized score anchor.
    """
    result: dict[str, Any] = {
        "status": "requirements_unverified",
        "explicit_technical_requirements": 0,
        "requirements_with_candidate_evidence": 0,
        "requirements_without_candidate_evidence": 0,
        "ambiguous_or_unparsed_requirements": 0,
        "final_score_authorized": False,
    }
    metadata = row.get("source_metadata")
    if (row.get("source_type") != "ats"
            or not isinstance(metadata, dict)
            or metadata.get("provider") != row.get("source_id")
            or not isinstance(row.get("description"), str)):
        return result
    groups, unresolved = _requirement_groups(row["description"])
    required = set().union(*groups) if groups else set()
    result["explicit_technical_requirements"] = len(required)
    result["ambiguous_or_unparsed_requirements"] = unresolved
    candidate_skills = _verified_skills(evidence)
    matched = len(required & candidate_skills)
    result["requirements_with_candidate_evidence"] = matched
    result["requirements_without_candidate_evidence"] = len(required) - matched
    if required:
        result["status"] = ("mapped_skills_have_evidence"
                            if matched == len(required) and not unresolved
                            else "incomplete_requirement_evidence")
    return result

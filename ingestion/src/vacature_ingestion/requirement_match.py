"""Evidence-bound technical requirement comparison for official ATS descriptions.

This is a conservative REVIEW AID, not a semantic eligibility decision, an
authenticity check or a match-score generator. Never infer candidate skills
from the role, missing evidence, employer snippets, or generic AI mentions.
CandidateEvidence is read in memory; no private claim or evidence ID is exported.
"""
from __future__ import annotations

import re
from datetime import datetime
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


def _verified_claims(evidence: list[dict[str, str]], *,
                     require_provenance: bool = False) -> list[str]:
    """Resolve positive claims without exporting private evidence or its IDs.

    The older aggregate matcher keeps its existing contract. New dimensions
    additionally require the live Register's source and verification fields.
    Presence of these fields is traceability, not independent source validation;
    the owning specialist must still verify the referenced source.
    """
    claims: list[str] = []
    for row in evidence:
        if (not isinstance(row, dict)
                or str(row.get("active", "")).casefold() != "true"
                or not isinstance(row.get("source_type"), str)
                or row.get("source_type") not in _ALLOWED_SOURCES
                or str(row.get("confidence", "")).casefold() not in {"high", "medium"}
                or not isinstance(row.get("evidence_id"), str)
                or not row["evidence_id"].strip()):
            continue
        claim = row.get("claim", "")
        if not has_positive_skill_claim(claim):
            continue
        if require_provenance:
            if any(not isinstance(row.get(key), str) or not row[key].strip()
                   for key in ("source_ref", "source_locator", "verified_at")):
                continue
            try:
                datetime.fromisoformat(row["verified_at"].strip().replace("Z", "+00:00"))
            except ValueError:
                continue
        claims.append(claim)
    return claims


def _verified_skills(evidence: list[dict[str, str]]) -> set[str]:
    # A portfolio index/GitHub profile URL, standing alone, is not skill proof.
    return set().union(*(_skill_tags(claim) for claim in _verified_claims(evidence)))


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


# Detailed dimensions remain literal review evidence. They do not certify that
# an entire natural-language requirement is met, or authorize a score.
_DIMENSION_HEADING = re.compile(
    r"(?<![A-Za-z0-9])(?P<label>Preferred (?:skills|qualifications)|"
    r"What you(?:'ll| will) do|Work style|How we work|Werkwijze)\s*:", re.I,
)
_OPTIONAL_SECTION = re.compile(
    r"^(?:nice[ -]to[ -]haves?|preferred(?: (?:skills|qualifications))?|bonus)\s*:?$", re.I,
)
_DUTY_SECTION = re.compile(
    r"^(?:responsibilities|your (?:role|tasks)|what you(?:'ll| will) do|"
    r"taken|verantwoordelijkheden)\s*:?$", re.I,
)
_STYLE_SECTION = re.compile(r"^(?:work style|how we work|werkwijze)\s*:?$", re.I)
_NON_REQUIREMENT = re.compile(
    r"\b(?:not required|not mandatory|do not (?:need|require)|"
    r"no experience (?:required|needed)|niet vereist|niet nodig|geen vereiste)\b", re.I,
)
_NOT_POSITIVE_DIMENSION = re.compile(
    r"\b(?:not|never|cannot|can't|unable to|without|niet|geen|"
    r"learning|interested in|plan to|would like to)\b|\bno\s+|"
    r"\b(?:0|zero)\s+(?:\w+\s+){0,3}(?:years?|experience|ervaring|projects?)\b", re.I,
)
_YEAR_FACT = re.compile(
    r"\b(?P<years>\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?|jaar)\s+"
    r"(?:(?:of\s+)?(?:professional\s+)?experience\s+(?:with|in|using)\s+|"
    r"ervaring\s+(?:met|in)\s+|(?:building|developing|using)\s+|"
    r"(?:of\s+)?(?=[^.;\n]{1,100}\s+experience\b))(?P<scope>[^.;\n]{1,180})",
    re.I,
)
_LANGUAGE_TERMS = {
    "en": r"english|engels", "nl": r"dutch|nederlands",
    "de": r"german|duits", "fr": r"french|frans", "es": r"spanish|spaans",
}
_LANGUAGE_TAGS = {key: re.compile(r"\b(?:" + words + r")\b", re.I)
                  for key, words in _LANGUAGE_TERMS.items()}
_LEVELS = {
    "native": r"native|moedertaal", "fluent": r"fluent(?:ly)?|fluency|vloeiend",
    "professional": r"business level|professional (?:proficiency|level)",
    **{level: level for level in ("a1", "a2", "b1", "b2", "c1", "c2")},
}
_LANGUAGE_ABILITY = re.compile(
    r"\b(?:speak|speaks|speaking|spoken|communicate|communication|"
    r"beheers|beheerst|spreek|spreekt|languages?|talen)\b", re.I,
)
_ACTIONS = {
    "develop": r"\b(?:build|built|building|develop|developed|developing|bouw|gebouwd|ontwikkel|ontwikkeld)\b",
    "maintain": r"\b(?:maintain|maintained|maintaining|onderhouden|onderhoud)\b",
    "test": r"\b(?:test|tested|testing|testen|getest)\b",
    "design": r"\b(?:design|designed|designing|ontwerp|ontworpen)\b",
    "automate": r"\b(?:automate|automated|automating|automatiseer|geautomatiseerd)\b",
}
_ACTION_PATTERNS = {key: re.compile(value, re.I) for key, value in _ACTIONS.items()}
_WORK_STYLES = {
    "asynchronous_collaboration": r"\b(?:asynchronous (?:communication|collaboration|work)|async[ -]first)\b",
    "independent_work": r"\b(?:work(?:ing)? independently|independent work|zelfstandig werk(?:en)?)\b",
    "cross_functional_collaboration": r"\b(?:cross[ -]functional collaboration|collaborat(?:e|ed|ing) with (?:design|product|engineering) teams?)\b",
}
_STYLE_PATTERNS = {key: re.compile(value, re.I) for key, value in _WORK_STYLES.items()}
_PROJECT = re.compile(r"\b(?:projects?|portfolio|plugins?|websites?|webshops?|stores?|themes?)\b", re.I)
_COMPLETED_PROJECT = re.compile(r"\b(?:built|developed|designed|shipped|delivered|launched|gebouwd|ontwikkeld|opgeleverd)\b", re.I)
_PROJECT_REQUIREMENT = re.compile(r"\b(?:portfolio|projects?|shipped|delivered|proven|demonstrat(?:ed|e|able))\b", re.I)


def has_positive_requirement_claim(claim: Any) -> bool:
    """Conservative positive-claim gate shared with final specialist receipts.

    Negative, zero-experience or aspirational claims cannot support a positive
    requirement. Ambiguous mixed claims remain unknown, never inability proof.
    """
    return has_positive_skill_claim(claim) and not bool(_NOT_POSITIVE_DIMENSION.search(claim))


def _scoped_years(clause: str) -> list[tuple[float, set[str]]]:
    """Do not sum years or transfer general experience to another skill."""
    if len(_NUMERIC_EXPERIENCE.findall(clause)) != 1 or _AMBIGUOUS.search(clause):
        return []
    match = _YEAR_FACT.search(clause)
    if match is None:
        return []
    scope = _skill_tags(match.group("scope"))
    # A later 'and ...' fact can describe different experience. Only one
    # named technology is mechanically comparable; mixed scope stays unknown.
    return [(float(match.group("years")), scope)] if len(scope) == 1 else []


def _language_specs(clause: str, *, candidate: bool = False) -> list[tuple[str, str]]:
    languages = [key for key, pattern in _LANGUAGE_TAGS.items() if pattern.search(clause)]
    if len(languages) > 1:
        pieces = re.split(r",|\band\b|\ben\b", clause, flags=re.I)
        parsed = [item for piece in pieces for item in _language_specs(piece, candidate=candidate)] if len(pieces) > 1 else []
        if len(parsed) == len(languages) and all(level != "unspecified" for _, level in parsed):
            return parsed
        return [] if candidate else [(language, "unparsed") for language in languages]
    if not languages:
        return []
    levels = [key for key, value in _LEVELS.items()
              if re.search(r"\b(?:" + value + r")\b", clause, re.I)]
    if len(levels) > 1:
        return [] if candidate else [(languages[0], "unparsed")]
    if candidate and not levels and not _LANGUAGE_ABILITY.search(clause):
        return []
    return [(languages[0], levels[0] if levels else "unspecified")]


def _language_level_matches(required: str, candidate: str) -> bool:
    cefr = ("a1", "a2", "b1", "b2", "c1", "c2")
    if required == "unparsed":
        return False
    if required == "unspecified" or required == candidate:
        return True
    # A fluency adjective is not an invented CEFR certificate/equivalence.
    return required in cefr and candidate in cefr and cefr.index(candidate) >= cefr.index(required)


def compare_requirement_dimensions(row: dict[str, Any],
                                   evidence: list[dict[str, str]]) -> dict[str, Any]:
    """Map explicit public requirements to traceable, literal candidate claims.

    Unknown prose and absent evidence remain unknown. Even a present literal
    match needs specialist interpretation of scope and level. No private claim,
    evidence ID, source locator, candidate duration or language level is emitted.
    """
    dimensions: dict[str, list[dict[str, Any]]] = {key: [] for key in (
        "mandatory_skills", "optional_skills", "experience_years", "languages",
        "responsibilities", "work_style", "projects",
    )}
    result: dict[str, Any] = {
        "status": "requirements_unverified", "dimensions": dimensions,
        "ambiguous_or_unparsed_requirements": 0,
        "semantic_review_required": True, "final_score_authorized": False,
    }
    metadata = row.get("source_metadata")
    description = row.get("description")
    if (row.get("source_type") != "ats" or not isinstance(metadata, dict)
            or metadata.get("provider") != row.get("source_id")
            or not isinstance(description, str)):
        return result
    claims = [claim for claim in _verified_claims(evidence, require_provenance=True)
              if has_positive_requirement_claim(claim)]
    candidate_clauses = [part for claim in claims
                         for part in re.split(r"(?<=[.!?;])\s+|\n", claim[:60_000])]
    candidate_skills = set().union(*(_skill_tags(claim) for claim in claims))
    candidate_years = [fact for clause in candidate_clauses for fact in _scoped_years(clause)]
    candidate_languages = [fact for clause in candidate_clauses
                           for fact in _language_specs(clause, candidate=True)]
    # Protect longer headings first: 'Preferred qualifications:' must not be
    # split again at 'Qualifications:' and turned into a mandatory section.
    text = _DIMENSION_HEADING.sub(lambda match: "\n" + match.group("label") + "\n", description[:60_000])
    text = _INLINE_HEADING.sub(lambda match: "\n" + match.group("label") + ":\n", text)
    unresolved = int(len(description) > 60_000 or len(text.splitlines()) > 300)
    section = "other"

    def add(dimension: str, item: dict[str, Any], present: bool) -> None:
        entry = {**item, "candidate_evidence": "present" if present else "unknown"}
        if entry not in dimensions[dimension]:
            dimensions[dimension].append(entry)

    for line in text.splitlines()[:300]:
        line = " ".join(line.strip().split()).lstrip("-*• ")
        heading = next((name for name, pattern in (
            ("required", _REQUIRED_SECTION), ("optional", _OPTIONAL_SECTION),
            ("responsibilities", _DUTY_SECTION), ("style", _STYLE_SECTION),
            ("other", _OTHER_SECTION),
        ) if pattern.fullmatch(line)), None)
        if heading:
            section = heading
            continue
        for clause in re.split(r"(?<=[.!?;])\s+", line):
            if not clause or _NON_REQUIREMENT.search(clause):
                continue
            kind = "optional" if section == "optional" or _OPTIONAL.search(clause) else "mandatory"
            requirement = section in {"required", "optional"} or bool(_REQUIREMENT_CUE.search(clause))
            if not requirement and section not in {"responsibilities", "style"}:
                continue
            if len(clause) > 900 or _AMBIGUOUS.search(clause):
                unresolved += 1
                continue
            tags = _skill_tags(clause)
            parsed = False
            if requirement:
                for skill in sorted(tags):
                    add(kind + "_skills", {"skill": skill}, skill in candidate_skills)
                    parsed = True
                if _NUMERIC_EXPERIENCE.search(clause):
                    years = _scoped_years(clause)
                    if not years:
                        unresolved += 1
                    for minimum, scope in years:
                        add("experience_years", {"minimum_years": minimum, "skills": sorted(scope), "kind": kind},
                            any(value >= minimum and scope <= skills for value, skills in candidate_years))
                        parsed = True
                for language, level in _language_specs(clause):
                    add("languages", {"language": language, "required_level": level, "kind": kind},
                        any(language == known and _language_level_matches(level, value)
                            for known, value in candidate_languages))
                    parsed = True
                    unresolved += int(level == "unparsed")
                if _PROJECT_REQUIREMENT.search(clause) and _PROJECT.search(clause):
                    add("projects", {"skills": sorted(tags), "kind": kind},
                        bool(tags) and not bool(re.search(r"\b\d+\b", clause)) and any(
                            tags <= _skill_tags(claim) and _COMPLETED_PROJECT.search(claim)
                            and _PROJECT.search(claim) for claim in candidate_clauses))
                    parsed = True
            if section == "responsibilities":
                for action, pattern in _ACTION_PATTERNS.items():
                    if pattern.search(clause):
                        add("responsibilities", {"action": action, "skills": sorted(tags)},
                            bool(tags) and any(len(_skill_tags(claim)) == 1
                                               and tags <= _skill_tags(claim) and pattern.search(claim)
                                               for claim in candidate_clauses))
                        parsed = True
            for style, pattern in _STYLE_PATTERNS.items():
                if pattern.search(clause):
                    add("work_style", {"style": style, "kind": kind},
                        any(pattern.search(claim) for claim in candidate_clauses))
                    parsed = True
            if not parsed:
                unresolved += 1
    result["ambiguous_or_unparsed_requirements"] = unresolved
    if any(dimensions.values()) or unresolved:
        result["status"] = "requirement_dimensions_review_only"
    return result

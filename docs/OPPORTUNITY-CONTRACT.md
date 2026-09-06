# Opportunity contract v1.0

`assess_opportunity()` geeft een **advisory** 0-100 score voor het moment waarop een al inhoudelijk beoordeelde vacature wordt gezien. De score staat volledig los van eligibility, kandidaatfit, salarisbeleid, de vaste matchscore en de bestaande ranking/tie-breaks.

## Invoer

Alle invoer moet uit expliciet bewijs komen:

- `age_hours`: geverifieerde publicatieleeftijd wanneer beschikbaar; anders mag de caller observation/first-seen-leeftijd gebruiken, maar die provenance moet buiten de engine als observation freshness worden gelabeld en mag niet als publicatiedatum worden gepresenteerd.
- `route_type`: `employer`, `ats`, `job_board` of `other`, bepaald na canonieke verificatie.
- `applicant_count`: alleen een expliciet zichtbaar applicant-signaal; onbekend blijft `None`.
- `deadline_hours`: alleen uit een expliciete geldige deadline; onbekend blijft `None`.
- `canonical_verified`: alleen `True` nadat de werkgever-/ATS-identiteit en actuele vacaturepagina zijn geverifieerd.

## Punten

- freshness: maximaal 35;
- directe routekwaliteit: maximaal 25;
- expliciet concurrentiesignaal: maximaal 20;
- expliciete deadline: maximaal 10;
- canonieke verificatie: maximaal 10.

Onbekende freshness, applicant count en deadline krijgen conservatieve neutrale punten plus een expliciete warning. De engine verzint geen ontbrekende signalen.

## Grenzen

De opportunity score:

- kan nooit een harde gate passeren of omzeilen;
- verandert nooit `core_fit`, `evidence_fit`, `workstyle_fit` of de matchscore;
- verandert de bestaande vacature-ranking niet;
- is geen voorspelling van aannemingskans;
- mag niet worden gebruikt om automatisch te solliciteren;
- is uitsluitend een tweede, uitlegbare prioriteitslaag voor reeds geschikte vacatures.

Wijzigingen aan deze score vereisen eigen contract-/evalcases. Wijzigingen aan de bestaande matchscore blijven daarnaast onder de afzonderlijke rankingbenchmark vallen.

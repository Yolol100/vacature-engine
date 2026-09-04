# Changelog

## 5.4.0 - 2026-09-04
- Observation contract verhoogd naar v1.1: alleen canonieke URL en `source_id + source_job_id` zijn nog automatische identiteitssleutels.
- `employer + title + location` blijft beschikbaar als duplicate-candidate fingerprint, maar mag verschillende sterke identiteiten niet meer automatisch samenvoegen.
- Canonicalisatie exposeert nu `published_at_candidates`, `published_at_conflict`, bronsoorten en duplicate-candidate metadata voor semantische verificatie door de Skill.
- Corrupte URL-poorten falen gesloten in plaats van een run te laten crashen.
- Nieuwe dependency-vrije `jobposting_signals()` normaliseert conservatieve Schema.org `JobPosting`-evidence zoals `datePosted`, `validThrough`, TELECOMMUTE, applicant locations, employment type, direct apply en ruwe salarisvelden.
- Structured data neemt nooit open-status-, remote-, geografie-, salarisnormalisatie- of fitbeleid over van de Skill/Config.
- Nieuwe regressietests dekken false-mergepreventie, URL-corruptie, publicatiedatumconflicten en structured-data-grenzen.

## 5.3.0 - 2026-08-30
- Runtime-taalpoort toegevoegd via `allowed_listing_languages`; de huidige `vacature-search`-flow geeft `nl,en` door vanuit live Config.
- Wanneer de taalpoort actief is, moeten vacaturetekst en sollicitatieflow in een toegestane taal zijn en mogen verplichte functie-/werktalen geen derde taal bevatten.
- Ontbrekende taalbewijzen falen gesloten zodra de taalpoort actief is; bestaande directe callers zonder taalconfig blijven backward compatible.
- Regressietests toegevoegd voor Nederlands/Engels, anderstalige listings/flows en verplichte derde talen.

## 5.2.0 - 2026-08-28
- Discoverycontract verduidelijkt voor wereldwijd remote werk: de Skill zoekt wereldwijd; de engine accepteert alleen vacatures die voor de kandidaat geografisch, juridisch, payroll- en timezone-technisch uitvoerbaar zijn.
- De kalenderjaarpoort is verwijderd. Alleen de echte leeftijd ten opzichte van `max_posting_age_days` bepaalt nu of een publicatiedatum te oud is.
- Salarisranges worden ondersteund via `salary_min_monthly_eur` en `salary_max_monthly_eur`; alleen een geverifieerde range die volledig onder de minimumgrens ligt wordt afgewezen.
- Exact salaris en range tegelijk, omgekeerde ranges en corrupte/niet-eindige bedragen falen gesloten als `salary_invalid`.
- Regressietests toegevoegd voor jaarovergang, wereldwijd remote compatibiliteit en salarisranges. De bestaande score-ankers en minimumscore blijven ongewijzigd.

## 5.1.0 - 2026-08-26
- Ongeldige salarisdata faalt nu gesloten: alleen expliciet `null` geldt nog als onbekend salaris; strings, booleans en niet-eindige getallen worden `salary_invalid`.
- Publicatiedatums accepteren alleen een ISO-datum of ISO-datetime en blokkeren suffix-smuggling.
- Actuele v5/v8 golden-, property/metamorphic-, adversarial- en gecontroleerde mutation-tests toegevoegd.
- Reproduceerbare source-release-evidence toegevoegd met SPDX 2.3 SBOM, package-verification-code, SHA-256 checksums en lokale provenance receipt.
- GitHub CodeQL, Dependabot, een deterministische dependency-policygate, CODEOWNERS, PR-template en SECURITY.md toegevoegd. Dependency Review zelf is niet bruikbaar zolang GitHub Dependency Graph op repositoryniveau uitstaat.
- Release Evidence workflow gebruikt GitHub artifact attestations met volledige commit-SHA-pinning van Actions.
- De build-backend is gepind op `setuptools==84.0.0` voor reproduceerbaardere build-inputs.

## 5.0.0 - 2026-08-26
- Veranderlijke gate- en outputdrempels zijn uit Python-constanten verwijderd en moeten expliciet uit `Config` worden doorgegeven.
- Nieuwe `VacancyPolicy` en `policy_from_config()` valideren de zes vereiste runtimewaarden en falen gesloten bij ontbrekende of ongeldige Config.
- De CLI accepteert nu expliciet `today`, `policy` en `vacancies`; de eerdere kapotte impliciete aanroep zonder `today` is verwijderd.
- Regressietests bewijzen dat wijzigingen in salarisgrens, leeftijdsgrens, outputlimiet en minimumscore direct het enginegedrag veranderen.
- De publieke package-export bevat geen dubbele runtime-drempelconstanten meer.

## 4.0.5 - 2026-08-26
- Kalenderjaarcontrole gebruikt nu dynamisch `today.year` in plaats van een vast 2026-jaar.
- `NaN` en `+/-inf` tellen niet meer als bekend salaris.
- Ongeldige losse records worden overgeslagen zonder de rest van de batch te blokkeren.
- Regressiedekking toegevoegd voor jaarwisseling, niet-eindige salarissen, kapotte records en de nieuwste-eerst tie-break.
- Exact gelijke kandidaten krijgen een stabiele technische tie-break op canonieke URL/titel zodat de top-10 niet van invoervolgorde afhangt.

## 4.0.4 - 2026-08-26
- De engine gebruikt geen impliciete hostdatum meer; `today` moet expliciet uit de canonieke Config-timezone komen.
- CI gebruikt actuele gepinde GitHub Actions en test Python 3.11, 3.12, 3.13 en 3.14.

## 4.0.3 - 2026-08-26
- Alleen sterke matches worden nog uitgevoerd: score >=75, eisenmatch >=40 en bewijs >=10.
- Nieuwe regressietests blokkeren zwakke bekende-salarismatches en bewaken de 75-puntgrens.

## 4.0.2 - 2026-08-26
- Repo en Skill gebruiken nu exact dezelfde vaste score-ankers, actualiteitspunten en tie-breaks.
- README compacter gemaakt zonder functionaliteit toe te voegen.

## 4.0.1 - 2026-08-25
- Onbekend salaris alleen als fallback bij minimaal 75/100.
- Boundary- en rankingtests uitgebreid.

## 4.0.0 - 2026-08-25
- Repo teruggebracht naar één eenvoudige filter/rank-helper.
- Alleen vaste filters, eenvoudige score en top-10; scraping, application- en auditlogica verwijderd.

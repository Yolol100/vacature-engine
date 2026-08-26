# Changelog

## 5.1.0 - 2026-08-26
- Ongeldige salarisdata faalt nu gesloten: alleen expliciet `null` geldt nog als onbekend salaris; strings, booleans en niet-eindige getallen worden `salary_invalid`.
- Publicatiedatums accepteren alleen een ISO-datum of ISO-datetime en blokkeren suffix-smuggling.
- Actuele v5/v8 golden-, property/metamorphic-, adversarial- en gecontroleerde mutation-tests toegevoegd.
- Reproduceerbare source-release-evidence toegevoegd met SPDX 2.3 SBOM, package-verification-code, SHA-256 checksums en lokale provenance receipt.
- GitHub CodeQL, dependency review, Dependabot, CODEOWNERS, PR-template en SECURITY.md toegevoegd.
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

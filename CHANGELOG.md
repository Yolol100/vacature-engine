# Changelog

## 4.0.5 - 2026-08-26
- Kalenderjaarcontrole gebruikt nu dynamisch `today.year` in plaats van een vast 2026-jaar.
- `NaN` en `+/-inf` tellen niet meer als bekend salaris.
- Ongeldige losse records worden overgeslagen zonder de rest van de batch te blokkeren.
- Regressiedekking toegevoegd voor jaarwisseling, niet-eindige salarissen, kapotte records en de nieuwste-eerst tie-break.

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

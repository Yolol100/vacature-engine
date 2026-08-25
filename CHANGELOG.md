# Changelog

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

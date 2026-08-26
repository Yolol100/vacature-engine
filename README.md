# vacature-engine

Kleine deterministische helper voor `vacature-search`.

Doet alleen:
1. harde vacaturefilters;
2. vaste 100-puntsscore;
3. sterke matches selecteren en maximaal 10 resultaten sorteren.

De Skill doet discovery, semantische beoordeling, bewijscontrole en motivatie.

## Contract

Harde gates: remote, compatibele regio, WordPress centraal, geen centrale mismatch, verifieerbare datum uit het actuele kalenderjaar van maximaal 120 dagen en bekend salaris >= EUR 3.500.

Score-input gebruikt alleen vaste ankers:
- `core_fit`: `0 / 25 / 40 / 50`
- `evidence_fit`: `0 / 10 / 18 / 25`
- `workstyle_fit`: `0 / 5 / 10 / 15`
- actualiteit: `10 / 8 / 6 / 4 / 2` voor `0-14 / 15-30 / 31-60 / 61-90 / 91-120` dagen

Een resultaat verschijnt alleen bij score >=75, `core_fit >=40` en `evidence_fit >=10`. Bekend salaris komt vóór onbekend salaris. Niet-eindige numerieke waarden (`NaN`, `+/-inf`) tellen niet als bekend salaris. Bij gelijke score: hogere eisenmatch -> hoger bewijs -> nieuwere vacature.

De aanroeper moet `today` altijd expliciet meegeven, bepaald met de canonieke timezone uit `Config`. De engine gebruikt nooit stil de host- of serverdatum en gebruikt `today.year` voor de kalenderjaarcontrole.

Ongeldige losse records worden overgeslagen zonder de rest van de batch te blokkeren. Directe `score()`-aanroepen blijven ongeldige score-ankers expliciet afwijzen.

```python
from vacature_engine import top_vacancies
best = top_vacancies(vacancies, today=today_from_config)
```

Geen scraping, e-mail of sollicitatieformulieren. `wordpress_related=true` mag alleen worden gezet wanneer WordPress aantoonbaar centraal staat.

# vacature-engine

Kleine deterministische helper voor `vacature-search`.

Doet alleen:
1. harde vacaturefilters;
2. vaste 100-puntsscore;
3. sterke matches selecteren en sorteren.

De Skill doet discovery, semantische beoordeling, bewijscontrole, cross-run deduplicatie, actieprioriteit en motivatie. Het `Vacature Register` is de enige runtime-bron voor veranderlijke configuratie en discovery-bronnen:
- `Config` bezit runtime-drempels, limieten, versies en bewijsinstellingen;
- `Bronnen` bezit bron-URL, status en `high`/`medium`-prioriteit;
- `Vacatures` bezit eerder verwerkte kandidaten voor cross-run deduplicatie.

De repo bevat daarom bewust geen vaste jobboardlijst, landenlijst, bronprioriteiten of veranderlijke vacaturedrempels. De vaste score-ankers en actualiteitsbanden zijn onderdeel van het engine-algoritme; alle veranderlijke output- en gate-drempels komen uit `Config`.

## Runtime-policy

De aanroeper moet per run expliciet deze Config-waarden doorgeven:
- `min_monthly_salary_eur`
- `max_posting_age_days`
- `max_output_roles`
- `min_output_score`
- `min_core_fit`
- `min_evidence_fit`

Ontbreekt een vereiste sleutel of is een waarde ongeldig, dan faalt de engine gesloten in plaats van een ingebouwde fallback te gebruiken.

## Scorecontract

Score-input gebruikt alleen vaste ankers:
- `core_fit`: `0 / 25 / 40 / 50`
- `evidence_fit`: `0 / 10 / 18 / 25`
- `workstyle_fit`: `0 / 5 / 10 / 15`
- actualiteit: `10 / 8 / 6 / 4 / 2` voor `0-14 / 15-30 / 31-60 / 61-90 / 91+` dagen

Bekend salaris komt vóór onbekend salaris. Niet-eindige numerieke waarden (`NaN`, `+/-inf`) tellen niet als bekend salaris. Bij gelijke score: hogere eisenmatch -> hoger bewijs -> nieuwere vacature. Exact gelijke kandidaten krijgen canonieke URL en titel als stabiele technische tie-break.

De aanroeper moet `today` altijd expliciet meegeven, bepaald met de canonieke timezone uit `Config`. De engine gebruikt nooit stil de host- of serverdatum en gebruikt `today.year` voor de kalenderjaarcontrole.

```python
from vacature_engine import top_vacancies

best = top_vacancies(vacancies, today=today_from_config, policy=config_values)
```

CLI-input is één JSON-object met dezelfde expliciete context:

```json
{
  "today": "2026-08-26",
  "policy": {
    "min_monthly_salary_eur": 3500,
    "max_posting_age_days": 120,
    "max_output_roles": 10,
    "min_output_score": 75,
    "min_core_fit": 40,
    "min_evidence_fit": 10
  },
  "vacancies": []
}
```

Geen scraping, discovery, bronprioritering, e-mail of sollicitatieformulieren. `wordpress_related=true` mag alleen worden gezet wanneer WordPress aantoonbaar centraal staat.

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

De repo bevat daarom bewust geen vaste jobboardlijst, landenlijst of bronprioriteiten. De vaste score-ankers en actualiteitsbanden zijn onderdeel van het engine-algoritme; veranderlijke output- en gate-drempels komen uit `Config`.

## Remote-first contract

Discovery is wereldwijd en wordt door de Skill uitgevoerd. Nederland is uitsluitend de huidige uitvoeringslocatie van de kandidaat voor de compatibiliteitscheck; het is nooit een filter op werkgever, vacatureland, jobboard, ATS of discoveryquery.

Twee remote-regels blijven hard:
- `fully_remote=true` is verplicht;
- `geography_compatible=true` is verplicht: de rol moet juridisch, contractueel en praktisch vanuit Nederland uitvoerbaar zijn.

Een landnaam, werkgeverland, vacatureland of tijdzoneverschil is op zichzelf geen blocker. Alleen concrete country-only-, payroll-, work-authorization-, legal-, security-, aanwezigheidseisen of expliciet onuitvoerbare verplichte werkuren/overlap blokkeren.

`wordpress_related=true` blijft vereist, maar de functietitel hoeft niet letterlijk `WordPress Developer` te zijn. De Skill mag deze vlag ook zetten voor aantoonbaar materiële WordPress-ecosysteemrollen, bijvoorbeeld WooCommerce, Elementor, Gutenberg, WordPress-support, maintenance, performance, technical SEO of bredere webdeveloperrollen. Een rol zonder materiële WordPress-relatie blijft uitgesloten.

De taal van het jobboard zelf is geen gate. Wanneer `allowed_listing_languages` uit Config actief is, moeten vacaturetekst, sollicitatieflow en verplichte functie-/werktalen aan die poort voldoen. De huidige Skill gebruikt `nl,en`.

## Runtime-policy

De normale `vacature-search`-aanroeper geeft per run expliciet deze Config-waarden door:
- `min_monthly_salary_eur`
- `max_posting_age_days`
- `max_output_roles`
- `min_output_score`
- `min_core_fit`
- `min_evidence_fit`
- `allowed_listing_languages`

De numerieke sleutels blijven verplicht. `min_monthly_salary_eur` is vanaf de remote-first policy een voorkeur, geen eligibility-gate. Een geldig bekend salaris onder de voorkeur krijgt `salary_below_preference`; een expliciet onbekend salaris krijgt `salary_unknown`. Beide mogen verder door de selectie. Ongeldige, conflicterende, niet-numerieke of niet-eindige salarisdata blijft fail-closed als `salary_invalid`.

`max_posting_age_days=0` betekent expliciet geen harde leeftijdslimiet. Bij een positieve waarde blijft de limiet actief. Een ontbrekende publicatiedatum mag door als waarschuwing `date_missing`; een ongeldige of toekomstige datum blijft een harde fout. Actualiteit blijft wel onderdeel van de score, zodat nieuwere vacatures hoger kunnen eindigen.

Wanneer de taalpoort actief is:
- `listing_language` moet in `allowed_listing_languages` staan;
- `application_language` moet in `allowed_listing_languages` staan;
- `required_languages` moet expliciet zijn geverifieerd;
- alleen een expliciete lege collectie betekent bewezen dat geen extra taal verplicht is;
- ontbrekend of ongeldig bewijs faalt gesloten;
- een geverifieerde verplichte taal buiten de toegestane set faalt gesloten.

## Scorecontract

Score-input gebruikt alleen vaste ankers:
- `core_fit`: `0 / 25 / 40 / 50`
- `evidence_fit`: `0 / 10 / 18 / 25`
- `workstyle_fit`: `0 / 5 / 10 / 15`
- actualiteit: `10 / 8 / 6 / 4 / 2` voor `0-14 / 15-30 / 31-60 / 61-90 / 91+` dagen

De score-ankers, `min_output_score`, `min_core_fit` en `min_evidence_fit` zijn niet versoepeld. Bekend salaris komt vóór onbekend salaris. Bij gelijke score: hogere eisenmatch -> hoger bewijs -> nieuwere vacature. Exact gelijke kandidaten krijgen canonieke URL en titel als stabiele technische tie-break.

De aanroeper moet `today` altijd expliciet meegeven, bepaald met de canonieke timezone uit `Config`.

```python
from vacature_engine import top_vacancies

best = top_vacancies(vacancies, today=today_from_config, policy=config_values)
```

Voorbeeld met de huidige remote-first leeftijdsinstelling:

```json
{
  "today": "2026-08-31",
  "policy": {
    "min_monthly_salary_eur": 3500,
    "max_posting_age_days": 0,
    "max_output_roles": 10,
    "min_output_score": 75,
    "min_core_fit": 40,
    "min_evidence_fit": 10,
    "allowed_listing_languages": "nl,en"
  },
  "vacancies": []
}
```

## Assurance

- CI test Python 3.11 t/m 3.14.
- Boundary-, golden-, property/metamorphic-, adversarial-, wereldwijde-geografie- en taalpoorttests bewaken het enginecontract.
- `scripts/mutation_smoke.py` bewaakt de huidige harde remote/geografie/WordPress-gates, scoregrenzen, unlimited-age-semantiek en salariswaarschuwing.
- CodeQL controleert coderisico; dependency-tests blokkeren ongewenste runtime-dependencies en ongepinde build-backends.
- Release-evidence blijft byte-reproduceerbaar met SPDX 2.3 SBOM, checksums en provenance receipt.

Geen scraping, discovery, bronprioritering, e-mail of sollicitatieformulieren in deze repo.

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

## Worldwide remote contract

Discovery is wereldwijd en wordt door de Skill uitgevoerd. Nederland is uitsluitend de huidige uitvoeringslocatie van de kandidaat voor de compatibiliteitscheck; het is nooit een filter op werkgever, vacatureland, jobboard, ATS of discoveryquery. Een werkgever in de VS, VK, EU, Azië of elders mag dus gewoon door wanneer de concrete functie juridisch, contractueel en praktisch vanuit Nederland kan worden uitgevoerd.

De engine gebruikt alleen `geography_compatible=true` wanneer de vacature daadwerkelijk uitvoerbaar is vanaf de huidige locatie van de kandidaat. Een expliciete Worldwide/Global/Anywhere-rol, internationale contractor/B2B-constructie of andere grensoverschrijdende remote rol kan dus door zonder dat `Netherlands` in de vacature staat. Een landnaam, werkgeverland, vacatureland of het tijdzoneverschil met dat land is op zichzelf geen gate. Alleen concrete country-only-, payroll-, work-authorization-, legal-, security- of aanwezigheidseisen blokkeren hard. Voor tijd geldt alleen een incompatibiliteit wanneer de vacature expliciete verplichte werkuren of overlap noemt die aantoonbaar niet uitvoerbaar zijn vanuit Nederland; leid dit nooit alleen af uit de tijdzone van het land. De engine zelf bevat geen vaste landenlijst en negeert niet-gating metadata zoals `employer_country` of `listing_country` voor eligibility.

Lokale discoverybronnen, bijvoorbeeld een landspecifiek Indeed-domein, zijn alleen vindkanalen en mogen de wereldwijde scope niet vernauwen. Als een externe jobwidget een geografie niet ondersteunt, is dat een toolbeperking en geen bewijs dat er geen geschikte vacatures bestaan; de Skill moet dan doorgaan via werkgever-, ATS- en web-discovery.

De taal van het jobboard zelf is geen gate. De concrete vacaturetekst, de sollicitatieflow en verplichte functie-/werktalen worden gecontroleerd wanneer `allowed_listing_languages` uit Config wordt meegegeven. De huidige `vacature-search` Skill vereist `nl,en`: de vacature en sollicitatie moeten dus volledig in Nederlands of Engels beschikbaar zijn en een derde taal mag niet verplicht zijn.

## Runtime-policy

De normale `vacature-search`-aanroeper geeft per run expliciet deze Config-waarden door:
- `min_monthly_salary_eur`
- `max_posting_age_days`
- `max_output_roles`
- `min_output_score`
- `min_core_fit`
- `min_evidence_fit`
- `allowed_listing_languages`

De zes numerieke sleutels blijven verplicht voor iedere engine-aanroep. De taalpoort wordt actief zodra `allowed_listing_languages` aanwezig is; de normale Skill-flow vereist deze sleutel en stopt vóór de engine-aanroep als hij ontbreekt. Directe oudere callers zonder deze sleutel houden alleen voor backward compatibility het eerdere gedrag zonder taalpoort.

Wanneer de taalpoort actief is:
- `listing_language` moet in `allowed_listing_languages` staan;
- `application_language` moet in `allowed_listing_languages` staan;
- `required_languages` moet expliciet zijn geverifieerd;
- alleen een expliciete lege collectie voor `required_languages` betekent bewezen dat geen extra taal verplicht is;
- ontbrekend, `null`, lege tekst of ongeldig `required_languages`-bewijs faalt gesloten;
- een geverifieerde verplichte taal buiten de toegestane set faalt gesloten.

Publicatiedatums accepteren een ISO-datum of ISO-datetime. Leeftijd is leidend; een vacature wordt niet afgewezen alleen omdat zij uit het vorige kalenderjaar komt zolang zij binnen `max_posting_age_days` valt.

Salaris kan als exact maandbedrag via `salary_monthly_eur` of als geverifieerde range via `salary_min_monthly_eur` en `salary_max_monthly_eur` worden aangeleverd. Gebruik nooit exact bedrag en range tegelijk. Alleen een expliciet onbekend salaris zonder deze numerieke velden activeert de onbekend-salarisfallback. Ongeldige, conflicterende of niet-eindige waarden worden `salary_invalid`. Een bekende range faalt de minimumgrens alleen wanneer de geverifieerde bovengrens volledig onder `min_monthly_salary_eur` ligt; een range die de grens bereikt of overlapt blijft eligible.

## Scorecontract

Score-input gebruikt alleen vaste ankers:
- `core_fit`: `0 / 25 / 40 / 50`
- `evidence_fit`: `0 / 10 / 18 / 25`
- `workstyle_fit`: `0 / 5 / 10 / 15`
- actualiteit: `10 / 8 / 6 / 4 / 2` voor `0-14 / 15-30 / 31-60 / 61-90 / 91+` dagen

Bekend salaris komt vóór onbekend salaris. Bij gelijke score: hogere eisenmatch -> hoger bewijs -> nieuwere vacature. Exact gelijke kandidaten krijgen canonieke URL en titel als stabiele technische tie-break.

De aanroeper moet `today` altijd expliciet meegeven, bepaald met de canonieke timezone uit `Config`. De engine gebruikt nooit stil de host- of serverdatum.

```python
from vacature_engine import top_vacancies

best = top_vacancies(vacancies, today=today_from_config, policy=config_values)
```

CLI-input is één JSON-object met dezelfde expliciete context:

```json
{
  "today": "2026-08-31",
  "policy": {
    "min_monthly_salary_eur": 3500,
    "max_posting_age_days": 120,
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
- `scripts/mutation_smoke.py` moet alle gecontroleerde kernmutaties doden.
- CodeQL controleert coderisico; `tests/test_dependency_policy.py` blokkeert runtime-dependencies en ongepinde build-backends. Dependabot bewaakt toekomstige dependency-updates.
- `scripts/build_release_bundle.py` bouwt tweemaal byte-reproduceerbare source-evidence met SPDX 2.3 SBOM, package-verification-code, SHA-256 checksums en een lokale provenance receipt.
- GitHub Actions op `main` maakt daarnaast artifact attestations; lokale `PROVENANCE.json` is geen vervanging voor die cryptografische attestation.
- `SECURITY.md` beschrijft private vulnerability reporting en release-eisen.

Branch protection is repository-instelling, geen bronbestand. Voor maximale governance moet `main` via GitHub Rules/Branch protection minimaal PR-review en de vereiste statuschecks afdwingen en force-push/delete blokkeren.

Geen scraping, discovery, bronprioritering, e-mail of sollicitatieformulieren. `wordpress_related=true` mag alleen worden gezet wanneer WordPress aantoonbaar centraal staat.

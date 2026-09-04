# vacature-engine

> **Portfoliostatus:** Actief ondersteunend · deterministische vacatureselectiehelper

`vacature-engine` ondersteunt `vacature-search`. De repo bezit geen discoverybeleid, kandidaatprofiel, bronprioriteiten of sollicitatiestatus. Veranderlijke runtimewaarheid blijft in het `Vacature Register`.

De engine doet alleen:
1. deterministische same-run observatiecanonicalisatie;
2. harde vacaturefilters;
3. vaste 100-puntsscore;
4. sterke matches selecteren en sorteren;
5. conservatieve normalisatie van Schema.org `JobPosting`-signalen.

Geen scraping, netwerkdiscovery, jobboardlijst, bronprioritering, e-mail of sollicitatieformulieren in deze repo.

## Observatiecontract v1.1

Gebruik `canonicalize_observations()` op door de Skill verzamelde `JobObservation`-records.

```python
from vacature_engine import canonicalize_observations

canonical = canonicalize_observations(observations)
```

Sterke automatische identiteit:
- genormaliseerde canonieke URL;
- `source_id + source_job_id`.

`employer + title + location` is alleen een zwak duplicate-candidate-signaal. Twee observaties met verschillende sterke identiteiten worden nooit alleen op die fingerprint automatisch samengevoegd. De Skill beslist zulke twijfelgevallen semantisch.

De canonicalisatielaag:
- verwijdert bekende trackingparameters en fragments uit publieke HTTP(S)-URL's;
- faalt gesloten op corrupte URL/port-data;
- geeft officiële werkgever-/ATS-evidence een stabiele canonicalisatievoorkeur;
- bewaart `source_ids`, `source_types`, `source_urls`, `first_seen_at`, `last_seen_at` en `observation_count`;
- exposeert `duplicate_candidate`, `duplicate_candidate_count` en de fingerprint voor semantische adjudicatie;
- exposeert alle gevonden `published_at_candidates` en `published_at_conflict`;
- promoveert `first_seen_at` nooit naar `published_at`;
- laat cross-run deduplicatie bij `Vacature Register:Vacatures`.

## Structured JobPosting contract v1.0

`jobposting_signals()` normaliseert alleen conservatieve signalen uit reeds opgehaalde Schema.org `JobPosting`-data.

```python
from vacature_engine import jobposting_signals

signals = jobposting_signals(jobposting_json, today=today_from_config)
```

De functie kan onder meer teruggeven:
- identifier, titel en hiring organization;
- `datePosted` en `validThrough` als valideerbare datumsignalen;
- `jobLocationType=TELECOMMUTE` als remote-signaal;
- `applicantLocationRequirements` als ruwe locatiesignalen;
- employment type en `directApply`;
- ruwe `baseSalary` currency/unit/value/min/max-signalen.

Deze data is aanvullend bewijs, geen beleidsbeslissing. De functie beslist nooit zelfstandig:
- of een vacature open is;
- `fully_remote`;
- `geography_compatible`;
- salarisconversie of maandloon;
- kandidaatfit of score.

Een verstreken geldige `validThrough` is een sterk expiry-signaal. Een toekomstige `validThrough` bewijst niet zelfstandig dat de vacature nog open is.

## Remote-first contract

Discovery is wereldwijd en gebeurt in de Skill. Nederland is alleen de uitvoeringslocatie van de kandidaat voor `geography_compatible`.

Hard vereist:
- `fully_remote=true`;
- `geography_compatible=true`;
- `wordpress_related=true`;
- geen centrale harde mismatch;
- actieve taalpoort moet passeren.

Een werkgeverland, vacatureland of tijdzoneverschil is op zichzelf geen blocker. Alleen concrete country-only-, payroll-, work-authorization-, legal-, security-, fysieke-aanwezigheids- of aantoonbaar onuitvoerbare verplichte werkuren/overlap blokkeren.

WordPress-gerelateerd mag ook aantoonbaar WooCommerce, Elementor, Gutenberg, support, maintenance, performance, technical SEO of breder webdevelopment omvatten wanneer WordPress materieel is.

## Runtime-policy

De caller geeft per run expliciet deze live Config-waarden door:
- `min_monthly_salary_eur`
- `max_posting_age_days`
- `max_output_roles`
- `min_output_score`
- `min_core_fit`
- `min_evidence_fit`
- `allowed_listing_languages`

`min_monthly_salary_eur` is een voorkeur. Geldig lager salaris krijgt `salary_below_preference`; onbekend salaris `salary_unknown`. Beide mogen verder. Corrupte salarisdata faalt gesloten als `salary_invalid`.

`max_posting_age_days=0` betekent geen harde leeftijdslimiet. Ontbrekende datum geeft `date_missing`; een ongeldige of toekomstige datum faalt gesloten.

Bij actieve taalpoort moeten vacaturetekst, sollicitatieflow en verplichte functie-/werktalen bewezen binnen de toegestane talen vallen.

## Scorecontract

Vaste ankers:
- `core_fit`: `0 / 25 / 40 / 50`
- `evidence_fit`: `0 / 10 / 18 / 25`
- `workstyle_fit`: `0 / 5 / 10 / 15`
- actualiteit: `10 / 8 / 6 / 4 / 2` voor `0-14 / 15-30 / 31-60 / 61-90 / 91+` dagen

De score-ankers en minimumfitdrempels veranderen niet zonder onafhankelijke benchmark. Bekend salaris komt vóór onbekend salaris. Bij gelijke score: hogere core -> hoger bewijs -> nieuwere vacature -> stabiele URL/titel-tie-break.

`today` moet altijd expliciet uit de canonieke Config-timezone komen.

```python
from vacature_engine import top_vacancies

best = top_vacancies(vacancies, today=today_from_config, policy=config_values)
```

## Assurance

- Python 3.11 t/m 3.14 in CI.
- Runtime-dependencies blijven leeg.
- Boundary-, golden-, property/metamorphic-, adversarial-, wereldwijde-geografie- en taalpoorttests.
- Observatietests bewaken sterke identiteit, false-mergepreventie, URL-fail-closed en publication-conflictprovenance.
- Structured-data-tests bewaken dat Schema.org-signalen nooit remote/geografie/open-statusbeleid overnemen.
- CodeQL en dependency-policygates blijven actief.
- Release-evidence blijft reproduceerbaar met SBOM, checksums en provenance receipt.

## Licentie

Deze repository bevat momenteel geen open-sourcelicentie. Hergebruik, distributie of afgeleide werken zijn niet toegestaan zonder expliciete toestemming van de rechthebbende.

# vacature-engine

Een kleine helper voor de `vacature-search` Skill.

De repo doet nog maar drie dingen:

1. Controleert de vaste vacature-eisen.
2. Berekent een eenvoudige matchscore.
3. Sorteert maximaal 10 vacatures van beste naar minste match.

Het zoeken op websites, het lezen van CV/portfolio en het schrijven van motivatiebrieven gebeurt door ChatGPT en de `vacature-search` Skill. Deze repo scrapt geen websites, verstuurt geen e-mail en vult geen sollicitatieformulieren in.

## Vaste filters

- volledig remote;
- salaris minimaal EUR 3.500 per maand wanneer gepubliceerd;
- onbekend salaris alleen als fallback bij een score van minimaal 75/100;
- geen expliciet onverenigbare country-only vacature;
- WordPress is verplicht als inhoudelijke kern;
- Elementor, WooCommerce, Gutenberg, ACF, PHP, front-end, performance, SEO en QA tellen alleen mee als ze duidelijk aan WordPress gekoppeld zijn;
- een algemene PHP-, React-, front-end-, SEO-, design-, QA- of supportrol zonder WordPress-focus valt af;
- alleen vacatures uit 2026;
- standaard maximaal 120 dagen oud;
- geen centrale harde mismatch.

## Score

- 50 punten: belangrijkste vacature-eisen;
- 25 punten: bewijs uit CV/portfolio/GitHub;
- 15 punten: werkwijze/senioriteit/dagelijkse stack;
- 10 punten: actualiteit.

## Gebruik

```python
from vacature_engine import top_vacancies

best = top_vacancies(vacancies)
```

Of via stdin:

```bash
python -m vacature_engine < vacancies.json
```

De input bevat al semantisch gecontroleerde velden. `wordpress_related=true` mag alleen worden gezet wanneer WordPress zelf of het WordPress-ecosysteem aantoonbaar centraal staat. De repo probeert vacaturetekst niet zelf te begrijpen; dat voorkomt dubbele logica tussen ChatGPT en Python.

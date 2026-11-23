# tarif-kwh

[![Collecte](https://github.com/raphaelh/tarif-kwh/actions/workflows/collecte.yml/badge.svg)](https://github.com/raphaelh/tarif-kwh/actions/workflows/collecte.yml)
[![Publication](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraphaelh.github.io%2Ftarif-kwh%2Fetat.json&query=%24.options.*.publication&label=publication)](https://raphaelh.github.io/tarif-kwh/etat.json)
[![Dernière vérification](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraphaelh.github.io%2Ftarif-kwh%2Fetat.json&query=%24.derniere_verification&label=derni%C3%A8re%20v%C3%A9rification)](https://raphaelh.github.io/tarif-kwh/etat.json)

État détaillé des derniers contrôles (par option, problèmes, remarques) et **date de la dernière vérification** :
[`etat.json`](https://raphaelh.github.io/tarif-kwh/etat.json) (voir [Signe de vie](#signe-de-vie)).

> **English** — Regulated French electricity prices (EDF *Tarif Bleu* / TRVE: Base, Peak/Off-peak, Tempo, EJP) as JSON,
> updated automatically twice a day from official sources (CRE deliberations and open data, EDF price sheets, Journal
> officiel) and cross-checked before publishing. Per option: kWh price and subscription, excl. and incl. tax, for every
> kVA rating, the current grid and the upcoming one with its effective date, plus full history since 2012. Ready to use
> in Home Assistant, Jeedom, Domoticz or any script: see the URLs below and the Home Assistant example.
> Human-readable tables (in French): <https://raphaelh.github.io/tarif-kwh/>.

Les prix réglementés de l'électricité en France (**TRVE**, « Tarif Bleu » résidentiel d'**EDF**), publiés en **JSON**
et mis à jour automatiquement depuis les sources officielles. Options couvertes : **Base**, **Heures Pleines / Heures Creuses**,
**Tempo** (bleu / blanc / rouge × HC / HP) et **EJP** (clients existants).

Pour chaque option : prix du kWh **HT et TTC**, abonnement annuel **HT et TTC** (et mensuel TTC) par puissance souscrite (kVA),
la **grille actuelle** et la **prochaine grille** avec sa date d'effet, dès que la CRE la propose (≈ 2 semaines avant le 1er février / 1er août).

👉 **Consulter les tarifs en clair** : [raphaelh.github.io/tarif-kwh/](https://raphaelh.github.io/tarif-kwh/), un tableau par option (TTC, HT dépliable).
L'abonnement mensuel y est l'annuel ÷ 12 : EDF facture l'abonnement annuel au prorata des jours.

Le JSON se lit avec n'importe quel outil : Home Assistant, Jeedom, Domoticz, tableur, script…

> ⚠️ **Projet non officiel**, sans lien avec EDF, la CRE ou les pouvoirs publics. « EDF », « Tempo » et « Tarif Bleu » sont des
> marques de leurs propriétaires, citées uniquement pour désigner les tarifs concernés. Les données sont reprises des
> publications officielles, sans garantie : en cas de doute, votre facture fait foi.

## Fichiers publiés

| Fichier | GitHub Pages | Brut |
|---|---|---|
| Page lisible (HTML) | https://raphaelh.github.io/tarif-kwh/ | — |
| Tout | https://raphaelh.github.io/tarif-kwh/tarifs.json | https://raw.githubusercontent.com/raphaelh/tarif-kwh/main/docs/tarifs.json |
| Base | https://raphaelh.github.io/tarif-kwh/base.json | …/docs/base.json |
| Heures Creuses | https://raphaelh.github.io/tarif-kwh/hphc.json | …/docs/hphc.json |
| Tempo | https://raphaelh.github.io/tarif-kwh/tempo.json | …/docs/tempo.json |
| EJP | https://raphaelh.github.io/tarif-kwh/ejp.json | …/docs/ejp.json |
| Historique depuis 2012 | https://raphaelh.github.io/tarif-kwh/historique.json | …/docs/historique.json |
| État des contrôles | https://raphaelh.github.io/tarif-kwh/etat.json | …/docs/etat.json |
| Schéma JSON | https://raphaelh.github.io/tarif-kwh/schema.json | …/docs/schema.json |

### Schéma JSON (`schema.json`)

Le format est décrit formellement en [JSON Schema 2020-12](docs/schema.json), pour ceux qui intègrent le flux dans
Jeedom, Domoticz ou un script : types, unités, statuts, puissances (kVA) et **périodes exactes de chaque option** (ex. les six
clés Tempo). Validez un fichier contre le schéma entier, ou contre une définition précise :
`schema.json#/$defs/fichier_option` (`base.json`, `hphc.json`, `tempo.json`, `ejp.json`), `#/$defs/fichier_tarifs`,
`#/$defs/fichier_historique`, `#/$defs/fichier_etat`.

```bash
pip install check-jsonschema
check-jsonschema --schemafile https://raphaelh.github.io/tarif-kwh/schema.json tempo.json
```

Règle de compatibilité : `schema_version` vaut `1`. Des champs peuvent être **ajoutés** sans changer de version (ne rejetez
pas les propriétés inconnues) ; toute suppression, tout renommage ou changement de sens fera passer `schema_version` à `2`.
Les tests du dépôt valident chaque fichier publié contre ce schéma.

### Signe de vie

Les tarifs ne changent que deux fois par an : la date d'un fichier ne dit pas si la collecte tourne encore. Le fichier
`etat.json` **servi par GitHub Pages** porte donc, en plus :

- `derniere_verification` : date du dernier passage **réussi** de la collecte (deux par jour) ;
- `sources_en_echec` : sources injoignables ou illisibles lors de ce passage (les autres ont été lues et recoupées).

Règle conseillée : **si `derniere_verification` a plus de 48 h, considérez les données comme peut-être périmées.**
Ces deux champs n'existent que sur GitHub Pages (`https://raphaelh.github.io/…`), pas dans la copie brute du dépôt
(`raw.githubusercontent.com`), où `etat.json` ne change qu'avec son contenu : le signe de vie ne crée aucun commit.
`mis_a_jour_le` reste, dans chaque fichier, la date du dernier changement de son contenu.

### Historique (`historique.json`)

Toutes les grilles entrées en vigueur, de la plus ancienne à l'actuelle : **depuis le 23/07/2012** pour toutes les
options (Tempo et EJP de 2012-2013 : abonnement TTC `null`). Tempo vient de l'open data CRE depuis août 2016 (statut `confirme` : HT
officiel, TTC tel que publié par la CRE, voir [Statuts de confiance](#statuts-de-confiance)), et d'avant (voir plus bas) des arrêtés et des grilles EDF archivées. Utile pour recalculer une facture
passée ou tracer l'évolution des prix.

```json
{
  "options": {
    "tempo": {
      "periodes": ["bleu_hc", "…"],
      "grilles": [
        {"date_debut": "2016-08-01", "date_fin": "2017-07-31", "statut": "confirme", "ttc_estime": false,
         "prix_ttc": {"bleu_hc": 0.1075, "…": 0}, "puissances": {"9": {"abonnement_ht": 92.04, "abonnement_ttc": 116.24, "prix_ht": {}, "prix_ttc": {}}},
         "sources": [{"type": "cre_opendata", "url": "…"}]},
        {"date_debut": "2026-08-01", "date_fin": null, "…": "…"}
      ]
    }
  }
}
```

- `date_fin` est le **dernier jour d'application (inclus)** ; `null` pour la grille en vigueur. Pour un jour `J`, prenez la
  grille telle que `date_debut <= J` et (`date_fin` nul ou `J <= date_fin`).
- Le TTC est celui **publié par la CRE avec les taxes de l'époque** (CSPE, TCFE, CTA, TVA à 5,5 % sur l'abonnement avant
  août 2025…). Une puissance absente n'était pas proposée à cette date (ex. Tempo 6 kVA avant février 2023 dans ces données).
- **Tempo, 2022 (février et août)** : l'open data CRE applique 10,9 €/MWh de taxes au kWh, contre 7,6 €/MWh pour
  Base et HP/HC. Les grilles Tarif Bleu EDF archivées de ces deux dates tranchent pour 7,63 €/MWh (TCFE 0,6630 + CSPE
  0,10 c€/kWh) : le TTC au kWh Tempo publié ici est recalculé (HT CRE + 7,63 €/MWh + TVA), égal au centime aux grilles
  EDF, avec `ttc_estime: true`, `statut: en_vigueur` et `correction_ttc` (motif, sources). L'abonnement reste celui de
  l'open data. Ces corrections sont listées dans [`config/corrections_opendata.json`](config/corrections_opendata.json).
- **Base, août 2015 et août 2016** : l'open data CRE y reprend le barème précédent (novembre 2014, puis août 2015). Le
  barème publié ici est celui des textes officiels (arrêté du 30 juillet 2015, délibération CRE du 13 juillet 2016),
  confirmé par les grilles Tarif Bleu EDF archivées : HT et abonnement HT du texte, abonnement TTC de la grille EDF, TTC
  au kWh = HT + taxes au kWh + TVA (`correction_ttc` avec `bareme: true`, `ttc_estime: true`, `statut: en_vigueur`).
  Août 2016 tombe au centime de la grille EDF ; août 2015 est 0,03 c€/kWh sous EDF, parce qu'il garde les TCFE de la CRE
  (≈ 0,93 c€ contre 0,957 c€ chez EDF), comme HP/HC à la même date.
- **Avant 2023, les taxes au kWh (CSPE + TCFE) changeaient au 1er janvier**, alors que le TTC de l'open data CRE est
  celui de la date d'effet. Quand une grille traverse un 1er janvier et que ces taxes ont bougé de plus de 0,5 €/MWh,
  une période s'ouvre au 1er janvier (`revision_ttc`, `ttc_estime: true`) : TTC au kWh recalculé avec les taxes de
  l'année, lues dans la première grille open data de cette année (même HT, même abonnement). C'est le cas au
  1er janvier 2014 (CSPE + 3 €/MWh, TVA 19,6 → 20 %), 2015 et 2016 (CSPE + 3 €/MWh), pour Base, HP/HC, Tempo et EJP. Les
  indexations annuelles des TCFE (≈ 0,1 €/MWh) se confondent avec l'arrondi de l'open data et ne sont pas reportées.
  Rien au 1er janvier 2022 : la baisse de 2022 (bouclier) date du 1er février, jour d'une nouvelle grille. Au
  **1er janvier 2023**, la TCCFE entre dans l'accise, seule taxe au kWh (1 €/MWh) : les grilles d'août 2022 de toutes
  les options sont révisées du 1er au 31 janvier 2023 avec l'accise de `config/taxes.json`.
- L'open data CRE paraît ≈ 4 semaines après la date d'effet : en attendant, la grille la plus récente vient des autres
  sources (même `statut` que dans `tempo.json`…).
- **Tempo d'août 2013 à juillet 2016**, avant l'open data CRE : le HT est le barème des arrêtés du 26 juillet 2013,
  du 30 octobre 2014 et du 30 juillet 2015, lu dans le jeu Jour Tempo (qui cite l'arrêté). Il est contrôlé par les cinq
  grilles Tarif Bleu EDF archivées de la période (août 2013, février 2014, janvier 2015, août 2015, janvier 2016,
  transcrites dans [`config/grilles_edf_archivees.json`](config/grilles_edf_archivees.json)) : chacune redonne le
  barème au centime, avec des taxes au kWh uniques et à moins de 0,5 €/MWh de celles de la CRE, sinon la grille est
  rejetée. Le TTC au kWh est calculé comme celui de l'EJP (HT + taxes au kWh de l'open data CRE + TVA,
  `ttc_estime: true`, `statut: en_vigueur`), révisé au 1er janvier : au plus 0,04 c€/kWh d'écart avec EDF (TCFE de la
  CRE). L'abonnement TTC est celui de la première grille EDF de la période (celle de janvier 2015 pour le barème de
  novembre 2014), révisé en 2014 comme celui des autres options (point suivant). Pas de 24 kVA : Jour Tempo lui donne
  toujours le barème du 30 kVA (jusqu'en février 2026), et cette puissance n'apparaît ni sur les grilles EDF ni dans
  l'open data avant la création du Tempo 24 kVA en août 2026. La grille EDF de janvier 2015 imprime 15,55 c€ en Blanc HC 36 kVA au
  lieu de 12,55 c€ : coquille corrigée dans la transcription.
- **Abonnement TTC en 2014 (Base, HP/HC, Tempo)** : le TURPE, dont la part fixe sert d'assiette à la CTA (27,04 %),
  change deux fois sans nouveau barème TRVE : TURPE 4 au **1er janvier 2014** (délibération CRE du 12 décembre
  2013), puis indexation au **1er août 2014** (délibération du 4 juin 2014). L'open data CRE garde l'abonnement d'août
  2013 jusqu'en octobre 2014. Ici, il est recalculé à ces deux dates (`revision_abonnement`, `ttc_estime: true`,
  `statut: en_vigueur` ; période 2014-08-01 → 2014-10-31 ajoutée) : CTA = 27,04 % × (gestion + comptage + soutirage
  fixe × kVA), soutirage « courte utilisation » pour la Base et au-delà de 18 kVA, « moyenne utilisation » pour HP/HC
  et Tempo jusqu'à 18 kVA ([`config/revisions_abonnement.json`](config/revisions_abonnement.json)). Cette règle
  redonne à 1 centime près l'open data d'août 2013 (TURPE 3), la grille EDF « en vigueur à compter du 1er février
  2014 » (TURPE 4 ; de −3,3 % à +0,9 % selon la puissance par rapport à 2013, +0,6 % en Base 6 kVA) et l'open data de
  novembre 2014 (TURPE d'août 2014). La date de la grille EDF de février n'est que celle de sa réédition : le TURPE 4,
  et donc la CTA, s'appliquent depuis le 1er janvier. L'EJP n'est pas concernée : son abonnement TTC vaut `null`
  avant août 2018.
- **Abonnement TTC HP/HC, août 2015 à juillet 2017** : l'open data CRE garde la CTA du TURPE d'août 2014, soit
  0,03 à 0,04 €/an de moins que la grille Tarif Bleu EDF du 1er août 2015, puis 0,13 à 1,37 €/an de moins que celle
  du 1er août 2016. L'abonnement est recalculé avec le TURPE du 1er août 2015 puis du 1er août 2016 (délibérations
  CRE du 28 mai 2015 et du 2 juin 2016, même règle, même fichier) et redonne les grilles EDF à 1 centime près,
  révision de janvier 2016 comprise (`revision_abonnement`, `ttc_estime: true`, `statut: en_vigueur`). La Base et
  Tempo de ces deux dates sont déjà justes : un abonnement à 1 centime près du calcul n'est pas touché.
- **Abonnement TTC Base, août 2017 à janvier 2018** : l'open data garde la CTA d'août 2016 (TURPE 4), au centime.
  Avec le TURPE 5 (délibération CRE du 17 novembre 2016 : gestion provisoire 6,96 €/an, comptage 19,80 €/an,
  courte utilisation 4,32 €/kVA/an), il vaut de 9,66 €/an de moins (15 kVA) à 1,43 €/an de plus (9 kVA). La même
  règle redonne au centime l'open data HP/HC et Tempo de cette date, qui ne sont pas touchés.
- **Abonnement TTC depuis 2018 : open data CRE ≠ grille EDF.** Les grilles Tarif Bleu EDF archivées suivent
  exactement la formule de la CTA (taux × (gestion + comptage + coefficient × kVA)), avec une version du TURPE par
  option et puissance : courte utilisation pour la Base, moyenne utilisation pour HP/HC jusqu'à 24 ou 30 kVA,
  versions à 4 plages depuis août 2022, courte utilisation à 4 plages pour tous depuis août 2025. L'open data CRE
  colle à ces versions jusqu'en 2019 (sauf Tempo, et HP/HC 24 kVA en février 2018), mais **depuis février 2020 elle
  ne correspond à aucune version** : la CRE y intègre un « TURPE optimisé », moyenne des options choisies client par
  client, estimée par EDF à partir de ses propres données (délibération TRVE n° 2026-06). L'abonnement TTC publié
  ici, celui de l'open data, s'écarte donc du montant affiché par EDF de −9 à +9 €/an selon l'option et la
  puissance (−4 à +7 €/an pour Tempo dès 2018). Ce n'est pas une erreur que l'on corrige : c'est la méthode de la
  CRE, et la CTA réellement facturée dépend encore de la version du TURPE retenue pour chaque client. Pour le
  montant affiché par EDF, voir sa grille Tarif Bleu. Deux cas particuliers :
  - **Tempo, août 2022 : abonnement TTC non mis à jour par la CRE.** Aucun prix HT ne change ce jour-là (bouclier
    tarifaire) ; la grille open data du 1er août 2022 ne sert qu'à reporter la hausse du TURPE dans la CTA. La Base
    et HP/HC la reçoivent (+0,5 à +1,9 €/an), EDF modifie aussi son abonnement Tempo, mais l'abonnement Tempo de
    l'open data reste identique au centime à celui de février 2022. Il est publié tel quel : avec le « TURPE
    optimisé », la bonne valeur de la CRE n'est pas calculable.
  - **Tempo 6 kVA, 2023** : puissance créée en février 2023, son abonnement suit exactement le TURPE « courte
    utilisation à 4 plages » jusqu'en août 2023, puis le « TURPE optimisé » comme les autres puissances à partir de
    février 2024 (+3,49 €/an). Changement de méthode, pas une erreur.
- **Tempo et EJP du 23 juillet 2012 au 31 juillet 2013** : ni l'open data CRE (Base et HP/HC seulement) ni Jour Tempo
  (depuis août 2013) ne les couvrent, et aucune grille EDF postérieure au mouvement n'a été archivée (la dernière est
  celle du 1er juillet 2012). Le barème HT est recopié à la main de l'arrêté du 20 juillet 2012 (JORF du 22 juillet,
  NOR DEVR1230094A) dans `config/baremes_arretes.json` (source `arrete`). Le **TTC au kWh** reprend les taxes au kWh
  de l'open data Base et HP/HC à la même date (2,28 c€/kWh, TVA 19,6 %), qui redonnent le TTC de l'open data Base au
  centime ; l'**abonnement TTC vaut `null`** (aucune grille EDF pour le vérifier). Tempo « 24-30 kVA » est publié en
  30 kVA seulement, comme en 2013-2016. Ce sont les tarifs de l'arrêté, réellement facturés à l'époque : le Conseil
  d'État l'a annulé en 2014 (tarifs jugés trop bas) et l'arrêté du 28 juillet 2014 a fixé pour cette période un
  barème plus élevé, appliqué sous forme de rattrapage sur les factures de 2014-2015 ; l'open data CRE de la Base
  garde lui aussi le barème de 2012.
- **Avant le 23 juillet 2012, rien** : l'open data CRE commence à cette date.
- **EJP** n'est pas dans l'open data CRE : son historique commence au **23 juillet 2012**. Le HT vient de la
  délibération CRE, du jeu Jour Tempo (depuis août 2013) et de l'arrêté du 20 juillet 2012 (avant) (qui cite l'arrêté du JORF ou la délibération CRE appliquée), le TTC de la
  grille EDF EJP archivée sur web.archive.org. Sans grille EDF, le TTC est calculé (`ttc_estime: true`) :
  - depuis février 2023 (août 2023, février 2026) : accise nationale et abonnement par la CTA calculée (voir plus bas) ;
  - **de juillet 2012 à janvier 2023** : le TTC comprenait des taxes locales (TCFE). On reprend les taxes au kWh
    (CSPE + TCFE) que la CRE a appliquées à Base, HP/HC et Tempo à la même date (open data, TVA 19,6 % avant 2014) :
    le **TTC au kWh** est donc celui de ses hypothèses, à 0,0003 €/kWh près (écart entre options). L'**abonnement TTC**
    est calculé par la CTA (voir plus bas) d'août 2018 à janvier 2023 ; il **vaut `null`**
    avant août 2018, faute de grille EDF pour vérifier le calcul (les grilles Tarif Bleu archivées de 2013 à 2016 n'ont pas d'EJP, la Wayback Machine n'a aucune grille EJP avant 2019, et la grille « février 2018 » recopiée par picbleu.fr est incohérente : abonnement TTC inférieur au HT + CTA). La méthode redonne au centime les TTC au kWh des grilles EDF de 2023 à 2026 ;
  - **2022** : 7,63 €/MWh, une fois Tempo corrigé (voir plus haut). La hausse de la pointe mobile au 1er février 2022
    (27,93 -> 77,72 c€/kWh HT, +178 %) est validée dans `config/validations.json` sur le barème de l'arrêté du
    28 janvier 2022.

  Une grille rejetée par les contrôles laisse un **trou** plutôt que de prolonger à tort la précédente.
- Pas de `prochaine` ici : elle est dans les fichiers par option.

L'historique de chaque fichier est aussi celui de git.

### Format (extrait de `tempo.json`)

```json
{
  "schema_version": 1,
  "option": "tempo",
  "periodes": ["bleu_hc", "bleu_hp", "blanc_hc", "blanc_hp", "rouge_hc", "rouge_hp"],
  "plages_horaires": {"hc": "22:00-06:00", "hp": "06:00-22:00"},
  "unites": {"prix": "EUR/kWh", "abonnement_ht": "EUR/an", "abonnement_ttc": "EUR/an", "abonnement_ttc_mensuel": "EUR/mois"},
  "actuelle": {
    "date_effet": "2026-08-01",
    "statut": "confirme",
    "ttc_estime": false,
    "prix_ttc": {"bleu_hc": 0.1356, "bleu_hp": 0.1654, "blanc_hc": 0.1536, "blanc_hp": 0.1921, "rouge_hc": 0.1615, "rouge_hp": 0.7295},
    "prix_ht": {"bleu_hc": 0.0824, "...": "..."},
    "puissances": {
      "6": {"abonnement_ht": 142.68, "abonnement_ttc": 189.98, "abonnement_ttc_mensuel": 15.8, "prix_ht": {}, "prix_ttc": {}}
    },
    "sources": [{"type": "cre_deliberation", "url": "https://www.cre.fr/…"}, {"type": "edf_grille", "url": "…"}, {"type": "cre_opendata", "url": "…"}],
    "taxes": {"accise_eur_kwh": 0.03062, "tva_energie": 0.2, "tva_abonnement": 0.2},
    "alertes": []
  },
  "prochaine": null,
  "mis_a_jour_le": "2026-11-23T09:00:00+00:00"
}
```

- `prix_ttc` / `prix_ht` au niveau de la grille n'existent que si le prix est **le même pour toutes les puissances**
  (vrai pour HP/HC, Tempo, EJP). En **Base**, le prix du kWh diffère entre ≤ 6 kVA et ≥ 9 kVA : lisez `puissances["6"].prix_ttc`.
- `prochaine` vaut `null` tant qu'aucune nouvelle grille n'est connue. Quand elle existe, **c'est à vous de l'appliquer à sa
  `date_effet`** (le fichier est aussi régénéré ce jour-là, mais votre outil peut ne pas le relire à minuit pile).
- **Heures creuses** : les plages HP/HC sont fixées par Enedis **pour chaque compteur** (voir votre facture ou votre espace
  client) ; elles ne sont donc pas publiées, sauf pour **Tempo** (HC de 22 h à 6 h pour tous) et EJP (pointe 7 h → 1 h).

### Statuts de confiance

| `statut` | Signification |
|---|---|
| `propose` | Grille proposée par la **délibération CRE**. Prix **HT officiels** ; TTC **calculé** (`ttc_estime: true`) avec les taxes connues : il peut différer de quelques dixièmes de centime si l'accise ou la CTA changent à la même date. |
| `en_vigueur` | **Date d'effet atteinte** sans texte signalé au Journal officiel, ou grille Tarif Bleu EDF concordante au centime près. Tant que `ttc_estime` vaut `true`, le TTC reste calculé (HT CRE + taxes). |
| `confirme` | L'**open data CRE** (HT et TTC, publié ≈ 4 semaines après) concorde. Le **HT** est alors sûr : recoupé avec les délibérations, les arrêtés et les grilles EDF, il n'a été trouvé faux qu'une fois (Base, août 2015 et août 2016). Le **TTC** est celui **publié par la CRE**, pas un TTC vérifié : la CRE recalcule elle-même les taxes et oublie parfois d'en reporter un changement (CTA, taxes au kWh). Les erreurs démontrées par un texte officiel ou une grille EDF sont corrigées, et la grille passe alors en `en_vigueur` (voir [Historique](#historique-historiquejson)). Le **prix du kWh TTC** a été comparé aux grilles Tarif Bleu EDF archivées : identique au centime, pour les trois options et toutes les puissances, à chaque date où une grille existe (août 2016, puis de février 2018 à août 2026, août 2018 compris grâce à une copie de la grille EDF sur lite.eco ; pas de grille retrouvée pour août 2017, juin 2019 et février 2021, où seul le prix Base relevé par des sites tiers concorde), une fois les corrections ci-dessus appliquées. L'**abonnement TTC**, lui, s'écarte de la grille EDF depuis 2018 (voir [Historique](#historique-historiquejson)). |

## Fonctionnement

Le collecteur ([`scripts/collect.py`](scripts/collect.py)) tourne dans GitHub Actions deux fois par jour. Une source = un module
de [`scripts/tarif_kwh/sources/`](scripts/tarif_kwh/sources), par ordre d'arrivée :

1. **Délibération CRE** « portant proposition des TRVE », annexe B (PDF, HT) — découverte sur la liste des délibérations et la
   page « Comprendre les TRVE » du site CRE, puis lue avec `pdfplumber` (barèmes Bleu résidentiel, métropole continentale,
   version standard). Les PDF déjà lus sont listés dans `data/registre.json` ; `config/sources.json` permet d'en forcer un
   (`annexes_b_anciennes` : annexes antérieures à juin 2025, dont la date d'effet doit être fournie).
2. **Grilles Tarif Bleu EDF** (PDF, TTC), source d'appoint : Base / HP-HC / Tempo, et une grille à part pour l'EJP (seule
   source officielle de l'abonnement EJP TTC). Le site d'EDF refuse les serveurs de GitHub (HTTP 403) : on ne contourne
   pas ce filtrage, on lit seulement la **dernière capture déjà faite par la Wayback Machine** (web.archive.org, copie
   brute identique au PDF d'EDF). Elle apporte le TTC officiel et l'accise appliquée, souvent dès le jour d'effet ; si
   aucune capture n'est disponible, rien n'est bloqué. `python scripts/collect.py --captures-edf` lit une fois toutes les
   captures EJP (amorçage de l'historique) ; une grille EDF sans grille HT à la même date est ignorée (ex. 1er novembre
   2024, où seul le TTC de l'abonnement change avec la CTA).
2 bis. **Jour Tempo** ([jeu data.gouv.fr](https://www.data.gouv.fr/datasets/tarifs-reglementes-delectricite-depuis-2014-base-heures-creuses-tempo-ejp-et-textes-officiels),
   Licence Ouverte) : barèmes HT, chaque valeur avec le texte officiel dont elle vient (son URL est celle de la source
   `jourtempo`). Lu pour l'EJP (depuis août 2013), recoupé avec la délibération CRE quand elle existe, et pour Tempo
   d'août 2013 à juillet 2016 seulement, avant l'open data CRE (contrôlé par les grilles EDF archivées de
   `config/grilles_edf_archivees.json`). Jamais pour Tempo ensuite, ni pour Base et HP/HC.
2 ter. **Arrêtés recopiés** (`config/baremes_arretes.json`, source `arrete`) : barèmes HT lus à la main au JORF, pour
   les dates qu'aucune autre source ne couvre (Tempo et EJP au 23 juillet 2012). Bloquant si une autre source HT
   existe à la même date (le barème recopié doit alors être retiré).
3. **Open data CRE** (`Option_Base.csv`, `Option_HPHC.csv`, `Option_Tempo.csv`) : lignes sans `DATE_FIN` pour la grille en
   cours ; toutes les lignes pour `historique.json`.
4. **Journal officiel** (flux ouvert DILA) : tout texte dont le titre parle de TRVE ou d'accise sur l'électricité ouvre une issue.

**CTA de l'EJP.** L'abonnement TTC vaut (HT + CTA) × (1 + TVA). Pour Base, HP/HC et Tempo, la CTA est déduite de l'open
data CRE. L'EJP n'y est pas : sa CTA est calculée, taux de CTA × (composante de gestion + composante de comptage +
soutirage fixe × kVA) du TURPE, d'après `config/taxes.json` (`cta_taux`, `turpe_part_fixe`, une période par
grille TURPE, en principe au 1er août). Le soutirage fixe est celui du tarif CU (sans différenciation temporelle)
jusqu'en juillet 2022 (`soutirage_fixe_cu`), puis du tarif CU4 (`soutirage_fixe_cu4`) ; le taux de CTA est de 27,04 %
jusqu'en juillet 2021. Ce calcul redonne au centime les grilles EDF d'août 2018, août 2019, août 2020 (recopiées par
picbleu.fr), février 2021 (comparateur-energies.com), août 2021 (Selectra, capture d'octobre 2021) — aucune n'étant
archivée chez EDF —, février 2023, février 2024, novembre 2024, février 2025, août 2025 et
août 2026 ; le JSON le signale par `taxes.cta_calculee`. Avant le TURPE 6, périodes configurées : août 2018 → juillet 2021
(TURPE 5 bis, CU), août 2021 → juillet 2022 (TURPE 6, CU, avec une composante de gestion de 13,92 € **déduite** de
la grille d'août 2021, la délibération ne la redonnant pas) et août 2022 → juillet 2023 (TURPE 6, CU4). Puis, sans trou, d'août 2023 à juillet 2027 : août 2023 → octobre 2024 (TURPE 6, indexation 2023, reportée), novembre 2024 → janvier 2025
(TURPE 6, indexation 2024 reportée au 1er novembre), février → juillet 2025 (TURPE 6, hausse exceptionnelle de 7,70 %),
puis TURPE 7 à partir d'août 2025. Deux garde-fous ouvrent une issue : une grille EJP
hors des périodes configurées (TURPE du 1er août pas encore ajouté), et un abonnement calculé qui diffère de plus d'un
demi-centime par mois de celui d'une grille EDF (période TURPE fausse ou taux de CTA changé sans être reporté).

Chaque source produit le même schéma commun (`scripts/tarif_kwh/schema.py`), puis `reconcile.py` recoupe :

- contrôles de cohérence par option : nombre de puissances et de prix, HP > HC, rouge HP le plus cher et bleu < blanc < rouge
  en HP (Tempo), pointe > normal (EJP), bornes plausibles, abonnement croissant avec la puissance, TTC > HT ;
- HT de la délibération = HT de l'open data ; HT + accise + TVA = TTC d'EDF ; TTC EDF = TTC open data ;
- variation de plus de 40 % par rapport à la grille précédente : acceptée seulement si deux sources concordent ou après
  validation manuelle dans `config/validations.json`.

**En cas d'échec de lecture ou de désaccord, rien de nouveau n'est publié pour l'option concernée** : son JSON précédent est
conservé, `etat.json` passe à `"publication": "bloquee"` et une **issue GitHub** (étiquette `alerte-tarif`) est ouverte.

### Taxes

TTC du kWh = (HT + accise) × 1,20 ; TTC de l'abonnement = (HT + CTA) × 1,20 (TVA à 20 % sur l'abonnement depuis le 1er août 2025).
La CTA dépend de la puissance et du tarif d'acheminement : elle est déduite de la dernière grille officielle.

L'**accise** est la seule taxe à suivre à la main, dans [`config/taxes.json`](config/taxes.json) : elle sert à estimer le TTC
d'une grille `propose` avant que le TTC officiel ne soit publié. Elle change par loi de finances (souvent au 1er février),
mais aussi en cours d'année (30,85 → 30,62 €/MWh au 1er août 2026). Trois garde-fous :

1. **Veille du Journal officiel** : toute loi de finances (initiale ou rectificative) et tout texte sur les accises de
   l'électricité ou de l'énergie ouvre une issue contenant la procédure.
2. **Contrôle a posteriori** : dès que la grille EDF ou l'open data CRE est connue, l'accise réellement appliquée
   (imprimée par EDF, ou TTC ÷ 1,2 − HT) est comparée à `config/taxes.json` ; tout écart ouvre l'issue
   « Accise à mettre à jour dans config/taxes.json ».
3. **Test du fichier** : dates croissantes, valeurs en €/kWh plausibles (une faute de frappe fait échouer la collecte
   avant toute publication).

Procédure : prendre le tarif « ménages et assimilés » en €/MWh (texte au JO, ou barème sur douane.gouv.fr), diviser
par 1 000, et ajouter `{"debut": "AAAA-MM-JJ", "valeur": 0.0xxxx, "source": "…"}` à `accise_eur_kwh` (l'éditeur web de
GitHub suffit). La collecte suivante recalcule les TTC estimés.

**Taxe changée en cours de grille.** Le TTC officiel d'une grille est celui de son jour d'effet. Si une ligne de
`config/taxes.json` (accise, TVA, taux de CTA, période TURPE pour l'EJP) prend effet **après** la date d'effet de la
grille en cours, sans nouveau barème, la grille `actuelle` des fichiers par option et de `tarifs.json` donne le **TTC du
jour** : recalculé à partir du HT avec les taxes en vigueur, `ttc_estime: true`, et `taxes.revision_ttc` (date et motifs).
Le statut et le HT ne changent pas. Une intégration qui lit le prix du kWh chaque jour (Home Assistant…) suit donc la taxe
dès la collecte du matin (5 h 17 UTC), à condition que la ligne ait été ajoutée à la configuration. Limite : pour
Base, HP/HC et Tempo, un changement de TURPE en cours de grille (rare : 1er novembre 2024) ne se recalcule pas, faute
de formule vérifiée ; seul l'abonnement serait touché. Dans `historique.json`, la grille garde le TTC publié jusqu'à la
veille du changement, puis une **période révisée** s'ouvre (même HT et mêmes sources, TTC recalculé, `ttc_estime: true`,
`revision_ttc`). C'est le cas de l'EJP au 1er novembre 2024 (TURPE reporté : seul l'abonnement change, et le calcul
redonne la grille EDF de ce jour au centime). L'open data CRE n'a pas de telle période pour Base, HP/HC et Tempo.

### Planification

- [`collecte.yml`](.github/workflows/collecte.yml) : deux fois par jour (+ lancement manuel, et à chaque modification de
  `docs/` ou `config/`). Il ne committe que si un JSON change, mais **redéploie le site GitHub Pages à chaque passage
  réussi** (signe de vie dans `etat.json`). Un passage en échec ne déploie rien : `derniere_verification` vieillit.
- GitHub désactive les workflows planifiés d'un dépôt sans activité depuis 60 jours. Les tarifs ne changeant que deux fois
  par an, chaque passage **réactive explicitement le workflow** par l'API GitHub (`PUT …/actions/workflows/collecte.yml/enable`),
  sans commit factice. Un échec du workflow vous est notifié par GitHub.
- Si, **7 jours avant le 1er février ou le 1er août**, aucune grille n'est connue pour cette échéance (délibération CRE non
  découverte, page CRE modifiée, blocage…), une issue « Délibération TRVE attendue non trouvée » est ouverte, avec la marche
  à suivre (ajouter l'annexe B dans `config/sources.json`). L'alerte reste active jusqu'à 45 jours après l'échéance.
- **Dependabot** propose chaque mois, par PR testée, les nouvelles versions des actions GitHub et des dépendances Python.

## Utilisation avec Home Assistant

Une intégration dédiée pourra venir plus tard (dépôt séparé `ha-tarif-kwh`). En attendant, ajoutez dans `configuration.yaml`
(ou un *package*) un capteur REST qui garde les deux grilles en attributs, puis des capteurs *template* qui **appliquent
la prochaine grille dès sa date d'effet** :

```yaml
rest:
  - resource: https://raphaelh.github.io/tarif-kwh/tempo.json
    scan_interval: 21600  # 6 h
    sensor:
      - name: Tarif kWh Tempo
        unique_id: tarif_kwh_tempo
        value_template: "{{ value_json.actuelle.date_effet }}"
        json_attributes:
          - actuelle
          - prochaine

template:
  - sensor:
      - name: Tempo prix bleu HC
        unique_id: tarif_kwh_tempo_bleu_hc
        unit_of_measurement: EUR/kWh
        state_class: measurement
        # Remplacez bleu_hc par bleu_hp, blanc_hc, blanc_hp, rouge_hc ou rouge_hp pour les autres capteurs.
        state: >
          {% set p = state_attr('sensor.tarif_kwh_tempo', 'prochaine') %}
          {% set g = p if p and p.date_effet <= now().date().isoformat()
                     else state_attr('sensor.tarif_kwh_tempo', 'actuelle') %}
          {{ g.prix_ttc.bleu_hc if g else none }}
        availability: "{{ state_attr('sensor.tarif_kwh_tempo', 'actuelle') is not none }}"

      - name: Tempo prix actuel
        unique_id: tarif_kwh_tempo_prix_actuel
        unit_of_measurement: EUR/kWh
        state_class: measurement
        # Couleur du jour : intégration « RTE Tempo » (adaptez le nom de l'entité).
        # Le jour Tempo va de 6 h à 6 h ; HC de 22 h à 6 h.
        state: >
          {% set p = state_attr('sensor.tarif_kwh_tempo', 'prochaine') %}
          {% set g = p if p and p.date_effet <= now().date().isoformat()
                     else state_attr('sensor.tarif_kwh_tempo', 'actuelle') %}
          {% set couleur = states('sensor.rte_tempo_couleur_actuelle') | lower %}
          {% set periode = 'hc' if now().hour >= 22 or now().hour < 6 else 'hp' %}
          {{ g.prix_ttc[couleur ~ '_' ~ periode] if g and couleur in ['bleu', 'blanc', 'rouge'] else none }}
```

Ce capteur « prix actuel » s'utilise directement dans le **tableau de bord Énergie** (« Utiliser une entité avec le prix actuel »).
Pour les autres options, changez l'URL (`base.json`, `hphc.json`, `ejp.json`) et les clés (`hp`, `hc`, `normal`, `pointe` ;
en Base : `g.puissances['6'].prix_ttc.base` selon votre puissance). L'abonnement est dans
`g.puissances['<kVA>'].abonnement_ttc` (€/an) et `abonnement_ttc_mensuel` (€/mois). Le mensuel est celui imprimé
sur la grille EDF quand elle existe : arrondi, il peut s'écarter d'environ 0,5 % de `abonnement_ttc` ÷ 12. Pour estimer un coût,
préférez l'annuel : EDF facture l'abonnement annuel au prorata des jours (la CTA réellement facturée peut varier de quelques
euros par an selon le contrat).

## Développement

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q                       # tests sur les PDF/CSV réels de tests/fixtures
.venv/bin/python scripts/collect.py       # collecte réelle -> docs/ et data/
.venv/bin/python scripts/collect.py --hors-ligne --date 2027-02-01   # simule une date
```

Ajouter une offre (ex. offres de marché EDF Zen Week-End, Zen Flex, Vert Électrique) : un module dans `sources/` produisant des
`GrilleSource`, une `OptionDef` dans `schema.py`. Ces prix libres n'ont qu'une source (PDF du fournisseur) sans recoupement
possible : ils devront porter un statut de confiance distinct (non prévu dans cette première version).

## Licence

Code sous licence MIT. Les données proviennent de la CRE (open data, Licence Ouverte), d'EDF et de la DILA.

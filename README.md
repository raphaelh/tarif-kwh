# tarif-kwh

[![Collecte](https://github.com/raphaelh/tarif-kwh/actions/workflows/collecte.yml/badge.svg)](https://github.com/raphaelh/tarif-kwh/actions/workflows/collecte.yml)
[![Publication](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraphaelh.github.io%2Ftarif-kwh%2Fetat.json&query=%24.options.*.publication&label=publication)](https://raphaelh.github.io/tarif-kwh/etat.json)

État détaillé des derniers contrôles (par option, problèmes, remarques) : [`etat.json`](https://raphaelh.github.io/tarif-kwh/etat.json).

> **English** — Regulated French electricity prices (EDF *Tarif Bleu* / TRVE: Base, Peak/Off-peak, Tempo, EJP) as JSON,
> updated automatically twice a day from official sources (CRE deliberations and open data, EDF price sheets, Journal
> officiel) and cross-checked before publishing. Per option: kWh price and subscription, excl. and incl. tax, for every
> kVA rating, the current grid and the upcoming one with its effective date, plus full history since 2012. Ready to use
> in Home Assistant, Jeedom, Domoticz or any script: see the URLs below and the Home Assistant example.

Les prix réglementés de l'électricité en France (**TRVE**, « Tarif Bleu » résidentiel d'**EDF**), publiés en **JSON**
et mis à jour automatiquement depuis les sources officielles. Options couvertes : **Base**, **Heures Pleines / Heures Creuses**,
**Tempo** (bleu / blanc / rouge × HC / HP) et **EJP** (clients existants).

Pour chaque option : prix du kWh **HT et TTC**, abonnement annuel **HT et TTC** (et mensuel TTC) par puissance souscrite (kVA),
la **grille actuelle** et la **prochaine grille** avec sa date d'effet, dès que la CRE la propose (≈ 2 semaines avant le 1er février / 1er août).

Le JSON se lit avec n'importe quel outil : Home Assistant, Jeedom, Domoticz, tableur, script…

> ⚠️ **Projet non officiel**, sans lien avec EDF, la CRE ou les pouvoirs publics. « EDF », « Tempo » et « Tarif Bleu » sont des
> marques de leurs propriétaires, citées uniquement pour désigner les tarifs concernés. Les données sont reprises des
> publications officielles, sans garantie : en cas de doute, votre facture fait foi.

## Fichiers publiés

| Fichier | GitHub Pages | Brut |
|---|---|---|
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

### Historique (`historique.json`)

Toutes les grilles entrées en vigueur, de la plus ancienne à l'actuelle : **depuis le 23/07/2012** pour Base et HP/HC,
**depuis 2016** pour Tempo (open data CRE, statut `confirme`, HT et TTC officiels). Utile pour recalculer une facture
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
- L'open data CRE paraît ≈ 4 semaines après la date d'effet : en attendant, la grille la plus récente vient des autres
  sources (même `statut` que dans `tempo.json`…).
- **EJP** n'est pas dans l'open data CRE : son historique ne commence qu'avec les délibérations lues par le collecteur.
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
| `confirme` | L'**open data CRE** (HT et TTC, publié ≈ 4 semaines après) concorde. |

## Fonctionnement

Le collecteur ([`scripts/collect.py`](scripts/collect.py)) tourne dans GitHub Actions deux fois par jour. Une source = un module
de [`scripts/tarif_kwh/sources/`](scripts/tarif_kwh/sources), par ordre d'arrivée :

1. **Délibération CRE** « portant proposition des TRVE », annexe B (PDF, HT) — découverte sur la liste des délibérations et la
   page « Comprendre les TRVE » du site CRE, puis lue avec `pdfplumber` (barèmes Bleu résidentiel, métropole continentale,
   version standard). Les PDF déjà lus sont listés dans `data/registre.json` ; `config/sources.json` permet d'en forcer un.
2. **Grille Tarif Bleu EDF** (PDF, TTC), source d'appoint. Le site d'EDF refuse les serveurs de GitHub (HTTP 403) : on ne
   contourne pas ce filtrage, on lit seulement la **dernière capture déjà faite par la Wayback Machine** (web.archive.org,
   copie brute identique au PDF d'EDF). Elle apporte le TTC officiel et l'accise appliquée, souvent dès le jour d'effet ;
   si aucune capture n'est disponible, rien n'est bloqué.
3. **Open data CRE** (`Option_Base.csv`, `Option_HPHC.csv`, `Option_Tempo.csv`) : lignes sans `DATE_FIN` pour la grille en
   cours ; toutes les lignes pour `historique.json`.
4. **Journal officiel** (flux ouvert DILA) : tout texte dont le titre parle de TRVE ou d'accise sur l'électricité ouvre une issue.

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

### Planification

- [`collecte.yml`](.github/workflows/collecte.yml) : deux fois par jour (+ lancement manuel). Il ne committe que si un JSON change.
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
`g.puissances['<kVA>'].abonnement_ttc` (€/an) et `abonnement_ttc_mensuel` (€/mois).

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

# tarif-kwh

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
| État des contrôles | https://raphaelh.github.io/tarif-kwh/etat.json | …/docs/etat.json |

L'historique de chaque grille est l'historique git de ces fichiers.

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
3. **Open data CRE** (`Option_Base.csv`, `Option_HPHC.csv`, `Option_Tempo.csv`) : lignes sans `DATE_FIN`.
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

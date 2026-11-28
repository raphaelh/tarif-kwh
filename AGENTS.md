# Contexte projet
Collecteur Python (pdfplumber, requests, jsonschema ; GitHub Actions deux fois par jour) qui publie en JSON les prix réglementés de l'électricité (TRVE Tarif Bleu) depuis les sources officielles ; contrainte critique : en cas d'échec de lecture ou de désaccord entre sources, rien de nouveau n'est publié pour l'option concernée.

## Commandes de vérification
- Test ciblé : `.venv/bin/pytest -q tests/test_config.py` (remplacer par le fichier de test concerné)
- Suite complète : `.venv/bin/pytest -q` (lit les PDF/CSV réels de `tests/fixtures`, plusieurs minutes)
- Lint / format : aucun
- Typecheck : aucun

## Règles
- Si le besoin ou un cas limite est ambigu, poser 2 ou 3 questions courtes avant de coder. Sinon, exécuter directement.
- Pour toute nouvelle logique métier ou correction de bug : écrire d'abord un test qui échoue, puis le code minimal qui le fait passer.
- Ne toucher qu'aux fichiers nécessaires. Pas de nouvelle dépendance sans demander.
- Ne jamais lire, afficher ni committer de secrets ou de fichiers `.env`.

## Pièges et décisions non évidentes
- `docs/` et `data/` sont produits et committés par le workflow `collecte.yml` : ne pas les éditer à la main, les régénérer avec `.venv/bin/python scripts/collect.py --hors-ligne`.
- Toute modification de `docs/`, `config/` ou `scripts/tarif_kwh/page.py` poussée sur main relance la collecte et redéploie le site.
- L'accise (`config/taxes.json`) est la seule taxe suivie à la main ; procédure dans la section « Taxes » du README.
- Le site d'EDF refuse les serveurs de GitHub (403) : on ne contourne pas ce filtrage, on lit seulement les captures de la Wayback Machine.
- Python minimum 3.12 (pyproject, CI 3.12 et 3.14).

## Définition de fini
Tests ciblés et suite concernée verts, lint et typecheck à 0, aucun log de debug ni changement hors sujet.

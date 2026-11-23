"""Page HTML lisible du site GitHub Pages : un tableau par option, à partir des JSON publiés."""
from __future__ import annotations

import json
from datetime import date, datetime
from html import escape
from pathlib import Path

MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre")
LIBELLES_PERIODES = {
    "base": "Base",
    "hp": "Heures pleines",
    "hc": "Heures creuses",
    "normal": "Heures normales",
    "pointe": "Pointe mobile",
}
LIBELLES_HORAIRES = {"hp": "HP", "hc": "HC"}
COULEURS_TEMPO = {"bleu": "Jours bleus", "blanc": "Jours blancs", "rouge": "Jours rouges"}
STATUTS = {
    "confirme": "confirmée",
    "en_vigueur": "en vigueur (non encore recoupée par l'open data CRE)",
    "propose": "proposée par la CRE, pas encore publiée au Journal officiel",
}
FICHIERS = ("tarifs.json", "base.json", "hphc.json", "tempo.json", "ejp.json", "historique.json", "etat.json", "schema.json")


def _date(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{'1er' if d.day == 1 else d.day} {MOIS[d.month - 1]} {d.year}"


def _horodatage(iso: str) -> str:
    t = datetime.fromisoformat(iso)
    return f"{_date(iso)} à {t:%H:%M} UTC"


def _nombre(v, decimales: int) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimales}f}".replace(".", ",")


def _entetes(periodes: list[str]) -> str:
    """En-tête du tableau ; Tempo a deux niveaux (couleur du jour, puis HC/HP)."""
    if all("_" in p for p in periodes):
        groupes: dict[str, list[str]] = {}
        for p in periodes:
            couleur, plage = p.split("_", 1)
            groupes.setdefault(couleur, []).append(plage)
        haut = "".join(
            f'<th colspan="{len(pl)}" scope="colgroup" class="tempo-{escape(c)}">{escape(COULEURS_TEMPO.get(c, c))}</th>'
            for c, pl in groupes.items()
        )
        bas = "".join(
            f'<th scope="col" class="num tempo-{escape(c)}">{escape(LIBELLES_HORAIRES.get(pl, pl))}</th>'
            for c, pls in groupes.items() for pl in pls
        )
        return (
            '<tr><th rowspan="2" scope="col">Puissance</th>'
            '<th colspan="2" scope="colgroup">Abonnement</th>'
            f"{haut}</tr>"
            '<tr><th scope="col" class="num">€/mois</th><th scope="col" class="num">€/an</th>'
            f"{bas}</tr>"
        )
    cols = "".join(f'<th scope="col" class="num">{escape(LIBELLES_PERIODES.get(p, p))}</th>' for p in periodes)
    return (
        '<tr><th rowspan="2" scope="col">Puissance</th>'
        '<th colspan="2" scope="colgroup">Abonnement</th>'
        f'<th colspan="{len(periodes)}" scope="colgroup">Prix du kWh (€)</th></tr>'
        '<tr><th scope="col" class="num">€/mois</th><th scope="col" class="num">€/an</th>'
        f"{cols}</tr>"
    )


def _tableau(grille: dict, periodes: list[str], taxe: str) -> str:
    """taxe : "ttc" ou "ht"."""
    lignes = []
    for kva, p in sorted(grille["puissances"].items(), key=lambda kv: int(kv[0])):
        an = p.get(f"abonnement_{taxe}")
        mois = p.get("abonnement_ttc_mensuel") if taxe == "ttc" else None
        if mois is None and an is not None:
            mois = round(an / 12, 2)
        prix = p.get(f"prix_{taxe}") or {}
        cellules = "".join(f'<td class="num">{_nombre(prix.get(per), 4)}</td>' for per in periodes)
        lignes.append(
            f'<tr><th scope="row">{escape(kva)} kVA</th>'
            f'<td class="num">{_nombre(mois, 2)}</td><td class="num">{_nombre(an, 2)}</td>{cellules}</tr>'
        )
    return (
        f'<div class="defile"><table><thead>{_entetes(periodes)}</thead>'
        f"<tbody>{''.join(lignes)}</tbody></table></div>"
    )


def _grille(titre: str, grille: dict, periodes: list[str]) -> str:
    statut = STATUTS.get(grille.get("statut", ""), grille.get("statut", ""))
    estime = " TTC calculé (pas encore publié par une source officielle)." if grille.get("ttc_estime") else ""
    return (
        f"<h3>{escape(titre.format(_date(grille['date_effet'])))}</h3>"
        f'<p class="meta">Grille {escape(statut)}.{escape(estime)} Prix du kWh en €.</p>'
        f"{_tableau(grille, periodes, 'ttc')}"
        "<details><summary>Hors taxes</summary>"
        f"{_tableau(grille, periodes, 'ht')}</details>"
    )


def _option(code: str, bloc: dict, etat: dict) -> str:
    periodes = bloc["periodes"]
    morceaux = [f'<section id="{escape(code)}"><h2>{escape(bloc["libelle"])}</h2>']
    if etat.get("publication") == "bloquee":
        morceaux.append(
            '<p class="alerte">Publication bloquée par les contrôles : la grille ci-dessous est la '
            "dernière publiée, elle n'est peut-être plus à jour.</p>"
        )
    infos = []
    if bloc.get("plages_horaires"):
        infos.append("Plages : " + ", ".join(
            f"{LIBELLES_HORAIRES.get(k, LIBELLES_PERIODES.get(k, k))} {v}" for k, v in bloc["plages_horaires"].items()
        ))
    if bloc.get("note"):
        infos.append(bloc["note"])
    if infos:
        morceaux.append("".join(f'<p class="note">{escape(i)}</p>' for i in infos))
    morceaux.append(_grille("En vigueur depuis le {}", bloc["actuelle"], periodes))
    if bloc.get("prochaine"):
        morceaux.append(_grille("Prochaine grille, à partir du {}", bloc["prochaine"], periodes))
    morceaux.append(
        f'<p class="lien">Données : <a href="{escape(code)}.json">{escape(code)}.json</a></p></section>'
    )
    return "".join(morceaux)


STYLE = """
:root{color-scheme:light dark;--fond:#fff;--texte:#1b1f24;--doux:#5b6470;--trait:#d8dde3;--entete:#f2f4f7;
--alerte:#fff4e5;--alerte-trait:#e5a000;--bleu:#dbe8ff;--blanc:#f4f4f4;--rouge:#ffe0dd;--lien:#0b5cad}
@media (prefers-color-scheme:dark){:root{--fond:#14171b;--texte:#e6e9ed;--doux:#9aa3ad;--trait:#323840;
--entete:#1f242a;--alerte:#3a2c10;--alerte-trait:#c88a00;--bleu:#1d2f4d;--blanc:#2a2e33;--rouge:#4a2421;--lien:#79b4f2}}
*{box-sizing:border-box}
body{margin:0;background:var(--fond);color:var(--texte);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:960px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.6rem;margin:0 0 .25rem}h2{font-size:1.25rem;margin:2.5rem 0 .5rem;padding-top:.5rem;border-top:1px solid var(--trait)}
h3{font-size:1rem;margin:1.25rem 0 .25rem}
.meta,.note,.lien,footer{color:var(--doux);font-size:.9rem;margin:.25rem 0}
nav{display:flex;flex-wrap:wrap;gap:.5rem 1rem;margin:1rem 0}a{color:var(--lien)}
.avertissement,.alerte{background:var(--alerte);border-left:4px solid var(--alerte-trait);padding:.6rem .8rem;font-size:.9rem;margin:1rem 0}
.defile{overflow-x:auto;margin:.5rem 0}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:.95rem}
th,td{border:1px solid var(--trait);padding:.35rem .6rem;text-align:left;white-space:nowrap}
thead th{background:var(--entete);font-weight:600}.num{text-align:right}
tbody th{font-weight:600}tbody tr:hover td,tbody tr:hover th{background:var(--entete)}
.tempo-bleu{background:var(--bleu)!important}.tempo-blanc{background:var(--blanc)!important}.tempo-rouge{background:var(--rouge)!important}
details{margin:.5rem 0}summary{cursor:pointer;color:var(--doux);font-size:.9rem}
code{font-size:.9em}
"""


def construire(tarifs: dict, etat: dict) -> str:
    options = tarifs.get("options", {})
    etats = etat.get("options", {})
    nav = "".join(f'<a href="#{escape(c)}">{escape(b["libelle"].rsplit(" - ", 1)[-1].removeprefix("option "))}</a>' for c, b in options.items())
    sections = "".join(_option(c, b, etats.get(c, {})) for c, b in options.items())
    verif = etat.get("derniere_verification")
    pied = [f"Dernière vérification des sources : {_horodatage(verif)}." if verif else ""]
    if etat.get("sources_en_echec"):
        pied.append("Sources en échec à ce passage : " + ", ".join(escape(s) for s in etat["sources_en_echec"]) + ".")
    fichiers = " · ".join(f'<a href="{f}">{f}</a>' for f in FICHIERS)
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prix du kWh Tarif Bleu</title>
<meta name="description" content="Prix du kWh et abonnements du Tarif Bleu EDF (Base, Heures Creuses, Tempo, EJP), mis à jour automatiquement.">
<style>{STYLE}</style>
</head>
<body><main>
<h1>Prix du kWh – Tarif Bleu</h1>
<p class="meta">Tarif réglementé de vente d'électricité, clients résidentiels, France métropolitaine continentale. Prix TTC, abonnement compris taxes.</p>
<p class="avertissement">{escape(tarifs.get("avertissement", ""))}</p>
<nav>{nav}</nav>
{sections}
<h2>Données</h2>
<p class="note">Les mêmes valeurs en JSON, pour Home Assistant ou tout autre outil : {fichiers}.</p>
<footer><p>{' '.join(p for p in pied if p)}</p>
<p>Code et méthode : <a href="https://github.com/raphaelh/tarif-kwh">github.com/raphaelh/tarif-kwh</a></p></footer>
</main></body>
</html>
"""


def ecrire_index(site: Path) -> None:
    """Écrit site/index.html à partir de site/tarifs.json et site/etat.json."""
    tarifs = json.loads((site / "tarifs.json").read_text(encoding="utf-8"))
    f_etat = site / "etat.json"
    etat = json.loads(f_etat.read_text(encoding="utf-8")) if f_etat.exists() else {}
    (site / "index.html").write_text(construire(tarifs, etat), encoding="utf-8")

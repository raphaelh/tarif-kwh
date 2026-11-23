"""Contrôles de cohérence d'une grille lue dans une source.

Chaque fonction renvoie une liste de problèmes (chaînes) ; liste vide = OK.
Un problème est BLOQUANT : l'option concernée n'est pas publiée.
"""
from __future__ import annotations

from .schema import OPTIONS, GrilleSource

# Bornes larges : servent à détecter une erreur de lecture (virgule décalée…)
KWH_MIN, KWH_MAX = 0.02, 2.0  # €/kWh
ABO_MIN, ABO_MAX = 20.0, 2000.0  # €/an
MENSUEL_MIN, MENSUEL_MAX = 2.0, 200.0  # €/mois
# Variation au-delà de laquelle une grille à source unique est jugée douteuse
VARIATION_MAX = 0.40


def _ordre_periodes(option: str, prix: dict[str, float], ou: str) -> list[str]:
    pb = []
    if option == "hphc" and not prix["hp"] > prix["hc"]:
        pb.append(f"{ou}: HP ({prix['hp']}) n'est pas > HC ({prix['hc']})")
    if option == "tempo":
        for c in ("bleu", "blanc", "rouge"):
            if not prix[f"{c}_hp"] > prix[f"{c}_hc"]:
                pb.append(f"{ou}: {c} HP n'est pas > {c} HC")
        if max(prix, key=prix.get) != "rouge_hp":
            pb.append(f"{ou}: rouge HP n'est pas le prix le plus élevé")
        if not prix["bleu_hp"] < prix["blanc_hp"] < prix["rouge_hp"]:
            pb.append(f"{ou}: HP bleu < blanc < rouge non respecté")
    if option == "ejp" and not prix["pointe"] > prix["normal"]:
        pb.append(f"{ou}: pointe mobile n'est pas > heures normales")
    return pb


def coherence(g: GrilleSource) -> list[str]:
    """Contrôles internes d'une grille (une source, une option, une date)."""
    opt = OPTIONS[g.option]
    pb: list[str] = []
    nom = f"{g.source} {g.option} {g.date_effet}"
    kvas = sorted(g.puissances)
    # Tempo d'avant août 2016 (Jour Tempo, arrêtés) : 9 à 36 kVA, sans 3 ni 6 kVA.
    minimum = 7 if (g.option, g.source) == ("tempo", "jourtempo") else opt.min_puissances
    if len(kvas) < minimum and g.source != "cre_opendata":
        pb.append(f"{nom}: {len(kvas)} puissances, {minimum} attendues au minimum")
    hors = set(kvas) - set(opt.puissances)
    if hors:
        pb.append(f"{nom}: puissances inattendues {sorted(hors)}")
    if not kvas:
        return pb + [f"{nom}: grille vide"]

    for champ, lo, hi in (
        ("abonnement_ht", ABO_MIN, ABO_MAX),
        ("abonnement_ttc", ABO_MIN, ABO_MAX),
        ("abonnement_ttc_mensuel", MENSUEL_MIN, MENSUEL_MAX),
    ):
        vals = [getattr(g.puissances[k], champ) for k in kvas]
        if all(v is None for v in vals):
            continue
        if any(v is None for v in vals):
            pb.append(f"{nom}: {champ} manquant pour certaines puissances")
            continue
        if any(not lo <= v <= hi for v in vals):
            pb.append(f"{nom}: {champ} hors bornes {vals}")
        if any(b < a for a, b in zip(vals, vals[1:])):
            pb.append(f"{nom}: {champ} ne croît pas avec la puissance {vals}")

    for k in kvas:
        p = g.puissances[k]
        for nature, prix in (("HT", p.prix_ht), ("TTC", p.prix_ttc)):
            if not prix:
                continue
            if set(prix) != set(opt.periodes):
                pb.append(f"{nom} {k} kVA: périodes {sorted(prix)} ≠ {sorted(opt.periodes)}")
                continue
            if any(not KWH_MIN <= v <= KWH_MAX for v in prix.values()):
                pb.append(f"{nom} {k} kVA: prix {nature} hors bornes {prix}")
            pb += _ordre_periodes(g.option, prix, f"{nom} {k} kVA {nature}")
        if p.prix_ht and p.prix_ttc:
            if any(p.prix_ttc[x] <= p.prix_ht[x] for x in p.prix_ht):
                pb.append(f"{nom} {k} kVA: TTC ≤ HT")
        if p.abonnement_ht and p.abonnement_ttc and p.abonnement_ttc <= p.abonnement_ht:
            pb.append(f"{nom} {k} kVA: abonnement TTC ≤ HT")
        if not p.prix_ht and not p.prix_ttc:
            pb.append(f"{nom} {k} kVA: aucun prix")
    return pb


def variations(nouvelle: dict, precedente: dict | None, seuil: float = VARIATION_MAX) -> list[str]:
    """Compare deux grilles publiées (format JSON) ; renvoie les écarts > seuil."""
    if not precedente:
        return []
    out = []
    for kva, p in nouvelle["puissances"].items():
        q = precedente["puissances"].get(kva)
        if not q:
            continue
        paires = [("abonnement_ht", p.get("abonnement_ht"), q.get("abonnement_ht"))]
        paires += [
            (f"prix_ht.{k}", v, q.get("prix_ht", {}).get(k)) for k, v in p.get("prix_ht", {}).items()
        ]
        for nom, a, b in paires:
            if a and b and abs(a / b - 1) > seuil:
                out.append(f"{kva} kVA {nom}: {b} → {a} ({(a / b - 1):+.0%})")
    return out

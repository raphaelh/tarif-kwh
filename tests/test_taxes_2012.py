"""Juillet-décembre 2012 : l'open data CRE applique les taxes au kWh de 2013 (CSPE 13,5 €/MWh) dès le 23 juillet 2012.

Corrigé avec les taxes de la grille EDF du 1er juillet 2012 (CSPE 1,05 + TCFE 0,914 c€/kWh) ; au 1er janvier 2013,
une période reprend le TTC de l'open data (``corrections_taxes_kwh`` de config/taxes.json)."""
import copy
from datetime import date

import pytest
from conftest import CSV

from tarif_kwh import publish, reconcile, taxes
from tarif_kwh.sources import cre_opendata

CONFIG = taxes.charger_config()


@pytest.fixture(scope="module")
def hist():
    od = {o: {"url": "u", "grilles": cre_opendata.parse_historique(p.read_bytes(), o)} for o, p in CSV.items()}
    taxes_od = reconcile.taxes_kwh_opendata(od, CONFIG)
    h = publish.construire_historique(od, None, {}, date(2026, 11, 23), None, CONFIG, taxes_od)
    return h, taxes_od


def _g(h, option, d):
    return next(g for g in h["options"][option]["grilles"] if g["date_debut"] == d)


def test_open_data_2012_taxes_de_2013(hist):
    _, taxes_od = hist
    assert taxes_od["2012-07-23"]["valeur"] == pytest.approx(0.0228)  # = août 2013, CSPE 13,5 comprise
    assert taxes_od["2013-08-01"]["valeur"] == pytest.approx(0.0228, abs=5e-5)


@pytest.mark.parametrize("option,kva,per,ttc_2012,ttc_2013", [
    ("base", "6", "base", 0.1225, 0.1263),  # (8,28 + 1,964) × 1,196 ; open data 12,63
    ("hphc", "6", "hp", 0.1353, 0.1391),
])
def test_correction_2012(hist, option, kva, per, ttc_2012, ttc_2013):
    h, _ = hist
    a, b = _g(h, option, "2012-07-23"), _g(h, option, "2013-01-01")
    assert (a["date_fin"], b["date_fin"]) == ("2012-12-31", "2013-07-31")
    assert a["puissances"][kva]["prix_ttc"][per] == ttc_2012
    assert b["puissances"][kva]["prix_ttc"][per] == ttc_2013
    assert a["correction_ttc"]["taxes_kwh"] == 0.01964 and a["statut"] == "en_vigueur" and a["ttc_estime"]
    assert b["revision_ttc"]["date"] == "2013-01-01" and "correction_ttc" not in b
    assert a["puissances"][kva]["abonnement_ttc"] == b["puissances"][kva]["abonnement_ttc"]


def test_correction_idempotente(hist):
    h, taxes_od = hist
    base = h["options"]["base"]["grilles"]
    assert publish._corrections_taxes_kwh(copy.deepcopy(base), taxes_od, CONFIG) == base

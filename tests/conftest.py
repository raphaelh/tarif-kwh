import csv
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "scripts"))
FIX = RACINE / "tests" / "fixtures"

ANNEXES = {
    "2025-08-01": FIX / "250619_2025-155_Proposition_TRVE_inf_36_annexe_B.pdf",
    "2026-02-01": FIX / "260114_2026-06_TRVE_2026_Annexe_B.pdf",
    "2026-08-01": FIX / "260715_2026-147_TRVE_Annexe_B.pdf",
}
CSV = {o: FIX / f"Option_{f}_2026-11-23.csv" for o, f in (("base", "Base"), ("hphc", "HPHC"), ("tempo", "Tempo"))}
EDF = FIX / "edf_grille_tarif_bleu_2026-08-01.pdf"
EDF_EJP = FIX / "edf_grille_ejp_2026-08-01.pdf"
EDF_EJP_2025 = FIX / "edf_grille_ejp_2025-08-01.pdf"  # capture archive.org


def fr(s: str) -> float:
    return float(s.replace(",", "."))


def lignes_csv(option: str, debut_jjmmaaaa: str) -> dict[int, dict]:
    """Lignes de l'open data CRE pour une grille donnée (toutes dates, pas seulement en cours)."""
    with open(CSV[option], encoding="utf-8-sig") as f:
        return {
            int(l["P_SOUSCRITE"]): l
            for l in csv.DictReader(f, delimiter=";")
            if l["DATE_DEBUT"] == debut_jjmmaaaa
        }


@pytest.fixture(scope="session")
def annexes():
    from tarif_kwh.sources.cre_deliberation import parse_annexe_b

    return {d: parse_annexe_b(p.read_bytes(), p.name) for d, p in ANNEXES.items()}

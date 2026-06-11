import pytest

from achat_immo.models import BienImmobilier, Scenario
from achat_immo.scenario_metrics import tri_annuel_approx, valeur_bien, van


def test_valeur_bien_applique_l_appreciation_composee() -> None:
    bien = BienImmobilier(ville="Nimes", surface_m2=40, prix_affiche=100_000)
    scenario = Scenario(appreciation_annuelle_pct=1.0)

    assert valeur_bien(bien, scenario, annee=2) == 102_010


def test_tri_annuel_approxime_un_flux_simple() -> None:
    assert tri_annuel_approx([-100, 110]) == pytest.approx(0.10, abs=1e-6)


def test_tri_annuel_retourne_none_si_aucune_racine_n_est_encadree() -> None:
    assert tri_annuel_approx([100, 110]) is None


def test_van_actualise_les_flux_annuels() -> None:
    assert van([-100, 60, 60], taux_actualisation_pct=10) == 4.13

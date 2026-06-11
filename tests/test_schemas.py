import math

import pytest
from pydantic import ValidationError

from achat_immo.models import EpoqueConstruction, ModeLocation, RegimeFiscal, TypeBien
from achat_immo.schemas import (
    AnnonceRecordSchema,
    HypothesesAchatRecordSchema,
    SimulationResultRowSchema,
)


def test_annonce_schema_coerce_les_valeurs_sql() -> None:
    schema = AnnonceRecordSchema.model_validate(
        {
            "id": "12",
            "ville": "Grenoble",
            "surface_m2": "42",
            "prix_affiche": "110000",
            "type_bien": "T2",
            "nb_pieces": "2",
            "epoque_construction": "apres_1990",
        }
    )

    assert schema.id == 12
    assert schema.type_bien == TypeBien.T2
    assert schema.nb_pieces == 2
    assert schema.epoque_construction == EpoqueConstruction.APRES_1990


def test_hypotheses_schema_valide_la_coherence_des_charges() -> None:
    with pytest.raises(ValidationError):
        HypothesesAchatRecordSchema.model_validate(
            {
                "loyer_hc_mensuel": 650,
                "mode_location": ModeLocation.MEUBLEE,
                "regime_fiscal": RegimeFiscal.LMNP_REEL,
                "charges_copro_annuelles": 300,
                "charges_recuperables_annuelles": 500,
            }
        )


def test_simulation_result_row_schema_accepte_alias_et_nan() -> None:
    row = SimulationResultRowSchema.model_validate(
        {
            "scenario": "central",
            "loyer_hc_mensuel": 650,
            "taux_credit": 3.6,
            "duree_annees": 20,
            "apport": 15_000,
            "vacance_mois": 1.0,
            "gestion_agence": 0,
            "mensualite_totale": 600,
            "montant_emprunte": 95_000,
            "cashflow_mensuel_avant_impot": -100,
            "cashflow_mensuel_apres_impot": -120,
            "effort_epargne_mensuel": 120,
            "rendement_net_avant_impot_pct": 4.2,
            "rendement_net_net_pct": 3.8,
            "tri": math.nan,
            "cash_on_cash": math.nan,
            "patrimoine_net_horizon": 20_000,
            "score": 60,
            "decision": "a_creuser",
        }
    )

    assert row.gestion_agence is False
    assert row.tri_annuel_pct is None
    assert row.cash_on_cash_return_pct is None
    assert row.patrimoine_net_sortie == 20_000

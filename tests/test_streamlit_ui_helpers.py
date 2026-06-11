from __future__ import annotations

from dataclasses import dataclass

from app import streamlit_app as ui
from achat_immo.models import ModeLocation, RegimeFiscal


def test_field_origins_identify_deduced_and_advanced_fields() -> None:
    assert ui.field_origin("loyer_hc_mensuel") == "Saisi"
    assert ui.field_origin("prelevements_sociaux_pct") == "Deduit"
    assert ui.field_origin("abattement_micro_bic_pct") == "Deduit"
    assert ui.field_origin("part_terrain_pct") == "Avance"
    assert ui.is_deduced_field("prelevements_sociaux_pct")
    assert ui.is_advanced_field("duree_amortissement_bien_annees")


def test_non_applicable_costs_are_forced_by_mode_and_regime() -> None:
    assert ui.effective_cfe_value(ModeLocation.NUE, 450.0) == 0.0
    assert ui.effective_cfe_value(ModeLocation.MEUBLEE, 450.0) == 450.0
    assert ui.effective_comptable_lmnp_value(RegimeFiscal.MICRO_BIC, 650.0) == 0.0
    assert ui.effective_comptable_lmnp_value(RegimeFiscal.LMNP_REEL, 650.0) == 650.0


def test_derived_fiscal_values_use_regime_constants() -> None:
    lmnp = ui.derived_fiscalite_values(RegimeFiscal.LMNP_REEL)
    nu = ui.derived_fiscalite_values(RegimeFiscal.LOCATION_NUE_REEL)

    assert lmnp["prelevements_sociaux_pct"] == 18.6
    assert nu["prelevements_sociaux_pct"] == 17.2
    assert lmnp["abattement_micro_bic_pct"] == 50.0
    assert nu["abattement_micro_foncier_pct"] == 30.0


def test_guided_interface_section_labels_are_centralized() -> None:
    assert ui.SIMULATION_SECTION_LABELS == ("Exploitation", "Strategies testees", "Analyse")
    assert ui.PORTFOLIO_DECISION_LABEL == "Decision portefeuille"


def test_grille_parametres_builder_filters_unknown_legacy_fields(monkeypatch) -> None:
    @dataclass(frozen=True)
    class LegacyGrilleParametres:
        prix_achats: tuple[float, ...] = ()
        comparer_regimes: bool = False

    monkeypatch.setattr(ui, "GrilleParametres", LegacyGrilleParametres)

    params = ui._build_grille_parametres(
        prix_achats=(100_000.0,),
        comparer_regimes=True,
        modes_location=(ModeLocation.MEUBLEE,),
        regimes_fiscaux=(RegimeFiscal.LMNP_REEL,),
    )

    assert params == LegacyGrilleParametres(
        prix_achats=(100_000.0,),
        comparer_regimes=True,
    )


def test_scenario_builder_filters_unknown_legacy_fields(monkeypatch) -> None:
    @dataclass(frozen=True)
    class LegacyScenario:
        horizon_annees: int = 10

    monkeypatch.setattr(ui, "Scenario", LegacyScenario)

    scenario = ui._build_scenario(
        horizon_annees=12,
        taux_actualisation_pct=4.5,
    )

    assert scenario == LegacyScenario(horizon_annees=12)

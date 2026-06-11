from achat_immo.fiscal_rules import (
    prelevements_sociaux_par_regime,
    regime_fiscal_recommande,
    regimes_compatibles,
)
from achat_immo.models import ModeLocation, RegimeFiscal


def test_regimes_compatibles_dependant_du_mode_location() -> None:
    assert regimes_compatibles(ModeLocation.MEUBLEE) == (
        RegimeFiscal.LMNP_REEL,
        RegimeFiscal.MICRO_BIC,
    )
    assert regimes_compatibles(ModeLocation.NUE) == (
        RegimeFiscal.LOCATION_NUE_REEL,
        RegimeFiscal.MICRO_FONCIER,
    )


def test_regime_recommande_reste_prudent() -> None:
    assert regime_fiscal_recommande(ModeLocation.MEUBLEE, 8_000) == RegimeFiscal.LMNP_REEL
    assert regime_fiscal_recommande(ModeLocation.NUE, 8_000) == RegimeFiscal.LOCATION_NUE_REEL
    assert regime_fiscal_recommande(ModeLocation.NUE, 20_000) == RegimeFiscal.LOCATION_NUE_REEL


def test_prelevements_sociaux_par_regime() -> None:
    assert prelevements_sociaux_par_regime(RegimeFiscal.LMNP_REEL) == 18.6
    assert prelevements_sociaux_par_regime(RegimeFiscal.MICRO_BIC) == 18.6
    assert prelevements_sociaux_par_regime(RegimeFiscal.LOCATION_NUE_REEL) == 17.2
    assert prelevements_sociaux_par_regime(RegimeFiscal.MICRO_FONCIER) == 17.2

# Simulateur d'investissement immobilier locatif

Ce projet remplace progressivement un tableur d'analyse locative par un moteur
Python versionnable, testable et exportable en CSV/Excel.

L'objectif n'est pas d'optimiser un rendement brut flatteur, mais de verifier
qu'un bien reste pertinent apres cout total projet, credit, vacance, charges,
gestion locative, fiscalite et cout d'opportunite face a un placement financier
type PEA/ETF World ou Nasdaq.

## Hypotheses prudentes par defaut

- vacance locative : 1 mois/an ;
- rendement calcule sur le cout total projet, pas seulement le prix affiche ;
- frais de notaire, travaux, meubles, frais bancaires et garantie inclus ;
- taxe fonciere, charges non recuperables, PNO, comptabilite LMNP et entretien inclus ;
- gestion agence activable avec frais en pourcentage des loyers encaisses ;
- LMNP reel modelise avec amortissement simplifie et extensible ;
- comparaison avec une alternative boursiere a 4 %, 6 %, 8 % ou 10 % possible.

## Architecture

```text
src/
├── achat_immo/
│   ├── models.py       # dataclasses metier
│   ├── loan.py         # mensualites, CRD, tableau d'amortissement
│   ├── cashflow.py     # loyers, charges, rendements, cash-flow
│   ├── taxes.py        # LMNP reel, nue reel, micro-BIC, micro-foncier
│   ├── scenarios.py    # simulations annuelles et alternative bourse
│   ├── comparison.py   # scoring et classement
│   ├── export.py       # CSV, Excel, Markdown
│   └── cli.py          # interface ligne de commande
```

Toute la surface publique du projet passe par `achat_immo.*`.

## Installation

Le projet utilise `uv`.

```bash
uv sync
```

Sur Mac avec dossier iCloud, l'installation editable peut produire un `.pth`
ignore par Python s'il porte un flag hidden. Pour executer la CLI ou verifier
un import package hors `pytest`, utiliser :

```bash
uv run --no-editable achat-immo --help
uv run --no-editable python -c "import achat_immo; print(achat_immo.__name__)"
```

Les tests utilisent `pythonpath = ["src"]` dans `pyproject.toml`.

## Exemple Python

```python
from achat_immo import (
    AlternativeInvestissement,
    BienImmobilier,
    Financement,
    Fiscalite,
    HypothesesLocation,
    TypeBien,
    scenario_central,
    simuler_bien_sur_horizon,
)

bien = BienImmobilier(
    ville="Grenoble",
    quartier="Championnet",
    surface_m2=42,
    prix_affiche=110_000,
    type_bien=TypeBien.T2,
    frais_notaire_estimes=8_800,
    travaux_estimes=5_000,
    meubles_estimes=4_000,
    dpe="D",
)

location = HypothesesLocation(
    loyer_hc_mensuel=700,
    charges_copro_annuelles=1_200,
    charges_recuperables_annuelles=500,
    taxe_fonciere=900,
    gestion_agence_active=True,
)

resultat = simuler_bien_sur_horizon(
    bien=bien,
    location=location,
    financement=Financement(apport=18_000, taux_credit_annuel_pct=3.6),
    fiscalite=Fiscalite(),
    scenario=scenario_central(horizon_annees=10),
    alternative=AlternativeInvestissement(rendement_annuel_pct=8),
)

print(resultat.indicateurs)
```

## CLI CSV

```bash
uv run --no-editable achat-immo data/annonces.csv --output outputs/comparaison.xlsx
```

Colonnes CSV utiles :

- `ville`, `quartier`, `adresse_approx`, `lien`
- `prix_affiche`, `prix_negocie`, `surface_m2`, `type_bien`, `dpe`
- `frais_agence_achat`, `frais_notaire_estimes`, `travaux_estimes`, `meubles_estimes`
- `frais_bancaires`, `garantie`
- `loyer_hc_estime`, `vacance_mois_par_an`
- `charges_copro_annuelles`, `charges_recuperables_annuelles`, `taxe_fonciere`
- `gestion_agence_bool`, `frais_gestion_pct`
- `assurance_pno`, `assurance_gli`, `comptable_lmnp`
- `apport`, `taux_credit`, `duree_credit_annees`, `assurance_emprunteur_pct`

Les colonnes absentes prennent des valeurs par defaut prudentes.

## Tests

```bash
uv run pytest -q
```

La suite couvre :

- mensualite et tableau d'amortissement ;
- cout total projet, rendement brut et rendement net ;
- cash-flow avec vacance et gestion agence ;
- LMNP reel simplifie ;
- comparaison avec placement financier alternatif ;
- scoring et export CSV.

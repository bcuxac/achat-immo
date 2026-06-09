# Simulateur d'investissement immobilier locatif

Ce projet remplace progressivement un tableur d'analyse locative par un moteur
Python versionnable, testable et exportable en CSV/Excel.

L'objectif n'est pas d'optimiser un rendement brut flatteur, mais de verifier
qu'un bien reste pertinent apres cout total projet, credit, vacance, charges,
gestion locative et fiscalite.

## Hypotheses prudentes par defaut

- vacance locative : 1 mois/an ;
- rendement calcule sur le cout total projet, pas seulement le prix affiche ;
- frais de notaire, travaux, meubles, frais bancaires et garantie inclus ;
- taxe fonciere, charges non recuperables, PNO, comptabilite LMNP et entretien inclus ;
- gestion agence activable avec frais en pourcentage des loyers encaisses ;
- LMNP reel modelise avec amortissement simplifie et extensible ;
- villes cibles fermees avec profils locaux pour borner les hypotheses legales ;
- plafond de loyer local applique automatiquement quand il est calculable ;
- diagnostic reglementaire separe du score financier ;
- decision robuste fondee sur toute la distribution des scenarios ;
- comparaison boursiere volontairement mise de cote pour l'instant.

## Architecture

```text
src/
├── achat_immo/
│   ├── models.py       # dataclasses metier
│   ├── loan.py         # mensualites, CRD, tableau d'amortissement
│   ├── cashflow.py     # loyers, charges, rendements, cash-flow
│   ├── taxes.py        # LMNP reel, nue reel, micro-BIC, micro-foncier
│   ├── scenarios.py    # simulations annuelles
│   ├── grids.py        # grilles automatiques loyer x taux x duree x apport
│   ├── city_profiles.py# profils locaux : villes ciblees, encadrement, plafonds
│   ├── diagnostics.py  # points bloquants, donnees manquantes et alertes metier
│   ├── robustness.py   # decision robuste, percentiles et conditions de validite
│   ├── storage.py      # stockage SQLite local
│   ├── comparison.py   # scoring et classement
│   ├── export.py       # CSV, Excel, Markdown
│   └── cli.py          # interface ligne de commande
app/
└── streamlit_app.py    # application locale de decision
```

Toute la surface publique du projet passe par `achat_immo.*`.

## Installation

Le projet utilise `uv`.

```bash
uv sync
```

Les tests utilisent `pythonpath = ["src"]` dans `pyproject.toml`.

## Application locale

```bash
uv run streamlit run app/streamlit_app.py
```

L'application utilise `data/achat_immo.sqlite` comme base locale. Cette base
est la memoire vivante du projet : annonces, hypotheses, runs de simulation,
resultats sauvegardes et decisions.

Excel devient optionnel : la discussion peut se faire directement dans
l'application via les vues annonce, simulations, comparaison et historique.

Workflow de l'application :

- `Nouvelle annonce` dans la barre laterale cree une fiche distincte dans SQLite ;
- `Tableau de bord` donne une vue base de donnees : annonces, statuts et derniers snapshots ;
- `Annonce` contient les donnees factuelles du bien ;
- `Hypotheses` contient les couts d'acquisition, charges et frais de modele ;
- `Simulations` estime le nombre de scenarios puis lance au clic les grilles loyer x taux x duree x apport x vacance x gestion ;
- les resultats de simulation sont centres sur le cash-flow mensuel de l'annee 1, le pret necessaire et une carte de decision ;
- la decision robuste affiche mediane, P10, part viable et conditions minimales observees avant le meilleur scenario ;
- `Comparaison` sert a comparer les meilleurs snapshots et a formaliser statut/notes ;
- `Historique` conserve les snapshots sauvegardes pour revenir sur une analyse passee.

## Exemple Python

```python
from achat_immo import (
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
)

print(resultat.indicateurs)
```

## CLI CSV

```bash
uv run achat-immo data/annonces.csv --output outputs/comparaison.xlsx
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
- grilles automatiques de scenarios ;
- stockage SQLite ;
- scoring et export CSV.

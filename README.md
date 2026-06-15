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
- fiscalite configurable par annonce : regime, TMI, prelevements sociaux, CFE, abattements et amortissements ;
- auto-remplissage auditable des hypotheses depuis l'annonce, avec confiance, source et explication ;
- tooltips sur les champs d'hypotheses pour expliciter l'impact modele et les sources utiles ;
- villes cibles fermees avec profils locaux pour borner les hypotheses legales ;
- plafond de loyer local applique automatiquement quand il est calculable ;
- diagnostic reglementaire separe du score financier ;
- décision robuste fondée sur toute la distribution des scénarios ;
- comparaison boursière volontairement mise de côté pour l'instant.

## Moteur Probabiliste (Monte Carlo)

Le simulateur dispose d'une couche d'analyse stochastique par méthode de Monte Carlo pour évaluer la robustesse d'une stratégie d'investissement face aux incertitudes (vacance locative, loyer effectif, travaux imprévus, plus-value, etc.).

**Principe :**
1. Vous définissez une `Strategy` (ville, type de bien, apport, régime fiscal...).
2. Vous configurez des distributions probabilistes pour les variables incertaines (ex: `TriangularDist`, `TruncatedNormalDist`).
3. Le moteur génère des centaines de scénarios et les évalue à travers le moteur de projection déterministe.
4. Les KPIs sont agrégés pour obtenir des statistiques robustes (TRI médian, TRI P10 pessimiste, probabilité de cash-flow négatif).

**Lancer un exemple :**
```bash
uv run python scripts/monte_carlo_grenoble.py
```

**Interpréter les résultats :**
- **TRI P50 (Médian)** : Le rendement le plus probable.
- **TRI P10 (Pessimiste)** : Dans 90% des cas, vous ferez mieux que ce chiffre. C'est l'indicateur de risque clé.
- **Probabilité de Cash-flow positif** : Estime votre chance de ne pas avoir à sortir de l'épargne tous les mois pour couvrir le projet.
- **Sensibilité** : Met en évidence les variables qui ont le plus d'impact sur votre rentabilité (via une corrélation de Spearman).

**Génération de Critères de Recherche :**
Plutôt que d'évaluer les annonces une par une, l'outil propose un Solver Inversé (`InverseSolver`). Il fait varier les paramètres d'entrée (prix d'achat max, loyer cible) pour trouver la "zone" mathématique qui satisfait vos objectifs probabilistes (ex: TRI P10 > 3%). Ces critères pourront ensuite être utilisés pour configurer un agent de sourcing automatique.

## Architecture

```text
src/
├── achat_immo/
│   ├── models.py       # dataclasses metier
│   ├── schemas.py      # validation pydantic
│   ├── engines/        # moteurs deterministes (credit, cashflow, taxes, projections)
│   ├── stochastic/     # moteur monte carlo, distributions, generateur
│   ├── analysis/       # statistiques et analyses de sensibilite
│   ├── search_policy/  # solver inverse generant les criteres de recherche
│   ├── deal_scoring/   # notation globale des annonces
│   ├── city_profiles.py# profils locaux : villes ciblees, encadrement, plafonds
│   ├── diagnostics.py  # points bloquants, donnees manquantes et alertes metier
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

Si une URL PostgreSQL est fournie via `DATABASE_URL` ou `[database].url` dans
les secrets Streamlit, l'application utilise cette base distante a la place du
fichier SQLite local. Ce mode est destine au deploiement cloud.

Excel devient optionnel : la discussion peut se faire directement dans
l'application via les vues annonce, simulations, comparaison et historique.

Workflow de l'application :

- `Nouvelle annonce` dans la barre laterale cree une fiche distincte dans SQLite ;
- `Tableau de bord` donne une vue base de donnees : annonces, statuts et derniers snapshots ;
- `Annonce` contient les donnees factuelles du bien ;
- `Hypotheses` contient les couts d'acquisition, charges et frais de modele ;
- `Hypotheses` propose des suggestions automatiques depuis l'annonce, applicables aux champs vides ou a toute la fiche ;
- `Hypotheses` contient aussi la fiscalite utilisee par les simulations : LMNP reel, micro-BIC, nue reel ou micro-foncier ;
- `Simulations` estime le nombre de scenarios puis lance au clic les grilles loyer x taux x duree x apport x vacance x gestion ;
- les resultats de simulation sont centres sur le cash-flow mensuel de l'annee 1, le pret necessaire et une carte de decision ;
- la decision robuste affiche mediane, P10, part viable et conditions minimales observees avant le meilleur scenario ;
- `Comparaison` sert a comparer les meilleurs snapshots et a formaliser statut/notes ;
- `Historique` conserve les snapshots sauvegardes pour revenir sur une analyse passee.

## Deploiement gratuit pour deux utilisateurs

Architecture cible :

- Streamlit Community Cloud execute l'application Python depuis le depot GitHub ;
- une base PostgreSQL gratuite, par exemple Supabase Free ou Neon Free, conserve les donnees ;
- les secrets Streamlit portent l'URL PostgreSQL et les mots de passe applicatifs ;
- SQLite reste le backend local par defaut pour developper et tester.

Le stockage local de Streamlit Community Cloud ne doit pas etre utilise comme
memoire durable. Le fichier `data/achat_immo.sqlite` est adapte au local, pas a
une application cloud qui doit conserver les ecritures apres redemarrage.

### Secrets Streamlit

Generer un hash par utilisateur :

```bash
uv run python scripts/hash_streamlit_password.py
```

Creer localement `.streamlit/secrets.toml` a partir de
`.streamlit/secrets.toml.example`, puis remplir :

```toml
[database]
url = "postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require"

[auth]
enabled = true

[auth.users]
benjamin = "pbkdf2_sha256$..."
compagne = "pbkdf2_sha256$..."
```

Le fichier `.streamlit/secrets.toml` est ignore par Git. Sur Streamlit
Community Cloud, coller le meme contenu dans les secrets de l'application.

### Migration SQLite vers PostgreSQL

Quand la base PostgreSQL est creee, migrer les donnees locales :

```bash
uv run python scripts/migrate_sqlite_to_postgres.py \
  --source data/achat_immo.sqlite \
  --target "postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require"
```

Ajouter `--replace` uniquement pour vider les tables PostgreSQL avant une
nouvelle importation initiale.

### Deploiement Streamlit Cloud

Parametres a renseigner dans Streamlit Community Cloud :

- repository GitHub du projet ;
- fichier principal : `app/streamlit_app.py` ;
- version Python : compatible avec `requires-python = ">=3.13"` ;
- secrets : bloc TOML ci-dessus.

Une fois deployee, l'application tourne dans l'environnement Python cloud de
Streamlit. Les telephones n'executent pas Python : ils affichent seulement
l'interface web. Les ecritures vont vers PostgreSQL.

## Exemple Python

```python
from achat_immo.models import (
    BienImmobilier,
    Financement,
    Fiscalite,
    HypothesesLocation,
    TypeBien,
)
from achat_immo.engines.scenarios import (
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

## Notes fiscales

La fiscalite reste une approximation de travail, pas un rescrit. Les valeurs par
defaut s'appuient sur les regles usuelles suivantes, a verifier lorsque la loi
change :

- location meublee longue duree au micro-BIC : seuil de recettes et abattement
  indiques par impots.gouv.fr ;
- prelevements sociaux 2026 : 18,6 % en location meublee et 17,2 % en location
  nue, appliques sur le revenu net taxable modelise ;
- location nue au micro-foncier : abattement forfaitaire de 30 % sous le seuil
  de revenus fonciers ;
- CFE : les loueurs en meuble peuvent y etre soumis.

Sources utiles :

- https://www.impots.gouv.fr/particulier/les-regimes-dimposition
- https://www.impots.gouv.fr/particulier/questions/je-donne-un-bien-en-location-dois-je-payer-des-prelevements-sociaux
- https://www.impots.gouv.fr/particulier/questions/je-fais-de-la-location-meublee-dois-je-payer-de-la-cfe-cotisation-fonciere-des
- https://bofip.impots.gouv.fr/bofip/3973-PGP.html

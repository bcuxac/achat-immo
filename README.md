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

## Cartographie de viabilite et analyse probabiliste

Le prefiltrage a grande echelle repose desormais sur une cartographie hors
ligne de biens hypothetiques. Pour une ville, un profil investisseur et des
objectifs donnes, un plan d'experiences Sobol couvre l'espace prix, surface,
loyer, charges non recuperables, taxe fonciere, travaux et apport. A Grenoble,
chaque plafond reste rattache a son secteur, son nombre de pieces, son epoque de
construction et son mode nu ou meuble. A Nimes, aucun plafond absolu au m2 n'est
invente : la ville est en zone tendue et le loyer precedent doit etre connu pour
verifier la relocation. Tous les biens sont evalues sous les memes chocs
economiques explicitement configures.

La carte distingue `rentable_et_autofinance`,
`rentable_cashflow_initial_positif`, `rentable_avec_effort_epargne`,
`rentabilite_fragile` et `sous_objectif_rentabilite`. Le cash-flow de reference
est le P10 de la premiere annee ; la pire annee et le cumul sur l'horizon restent
publies comme indicateurs de risque sans devenir des synonymes de rentabilite.
Un Monte Carlo propre au bien et le solveur inverse
restent necessaires dans un second temps pour les opportunites preselectionnees.

Construire la carte de la ville du profil actif :

```bash
uv run python scripts/build_viability_map.py --properties 512 --scenarios 500 --workers 1
```

Les fichiers generes sont places dans `outputs/viability/` et ne sont pas
versionnes. Leur fichier de metadonnees contient toute la configuration utile a
la reproductibilite, les categories reglementaires et leurs sources.

## Monte Carlo propre a une opportunite

Le simulateur dispose d'une couche d'analyse stochastique par méthode de Monte Carlo pour évaluer la robustesse d'une stratégie d'investissement face aux incertitudes (vacance locative, loyer effectif, travaux imprévus, plus-value, etc.).

**Principe :**
1. Vous définissez une `Strategy` (ville, type de bien, apport, régime fiscal...).
2. Vous configurez des distributions probabilistes pour les variables incertaines (ex: `TriangularDist`, `TruncatedNormalDist`).
3. Le moteur génère des centaines de scénarios et les évalue à travers le moteur de projection déterministe.
4. Les KPIs sont agrégés pour obtenir des statistiques robustes (TRI médian, TRI P10 pessimiste, probabilité de cash-flow négatif).

**Interpréter les résultats :**
- **TRI P50 (Médian)** : Le rendement le plus probable.
- **TRI P10 (Pessimiste)** : Dans 90% des cas, vous ferez mieux que ce chiffre. C'est l'indicateur de risque clé.
- **Probabilité de Cash-flow positif** : Estime votre chance de ne pas avoir à sortir de l'épargne tous les mois pour couvrir le projet.
- **Sensibilité** : Met en évidence les variables qui ont le plus d'impact sur votre rentabilité (via une corrélation de Spearman).

**Génération de Critères de Recherche :**
Pour une opportunite preselectionnee, le solveur inverse (`InverseSolver`) fait
varier le prix d'achat afin de calculer le prix maximal compatible avec les
objectifs probabilistes, par exemple un TRI P10 superieur a 3 %.

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
│   ├── viability/      # cartographie hors ligne des zones viables
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
l'application via un workflow centre sur l'import d'URLs, le pipeline
d'opportunites et la fiche de decision.

Workflow de l'application :

- `Pipeline` montre les opportunites a traiter, leurs statuts et les actions
  prioritaires ;
- `Queue sourcing` sert a ajouter des URLs, surveiller leur traitement et
  depanner manuellement les cas bloques ;
- `Fiche annonce` regroupe tout ce qui concerne une seule annonce : synthese,
  donnees extraites, hypotheses, analyse financiere, preuves et decision ;
- `Comparaison` arbitre uniquement les opportunites shortlistees ou actives ;
- `Parametres / Automatisation` explicite les secrets attendus, le workflow
  GitHub Actions, les limites operationnelles et le profil d'investissement.

### Profil d'investissement versionne

La page `Parametres / Automatisation` permet de modifier le budget total,
l'apport, le financement, la TMI, l'horizon, les objectifs de rentabilite, les
budgets de calcul, les bornes d'exploration et chaque cout annuel utilise par la
carte. Ces bornes sont des choix de simulation explicites, pas des donnees de
marche inferees. Chaque enregistrement ajoute
une version immuable identifiee par un hash. La cartographie, le sourcing et les
relances manuelles lisent ce profil ; les analyses enregistrent son hash dans
leurs diagnostics.

Les baremes fiscaux et plafonds legaux ne sont pas des preferences utilisateur :
ils restent versionnes dans le code et testes separement. L'inventaire des
valeurs encore a traiter est maintenu dans `docs/configuration_audit.md`.

### Acquisition des annonces Jinka

L'acquisition est separee en trois etapes : les emails Jinka signalent une
alerte, une session Jinka authentifiee developpe cette alerte en URLs
d'annonces, puis le pipeline existant charge et extrait uniquement ces fiches.
Les parametres `alert_id`, `utm_*` et `from` sont retires de l'identite d'une
fiche afin qu'une meme annonce ne soit jamais ajoutee plusieurs fois.

Pour charger un historique initial, exporter les messages au format EML/MBOX,
ou fournir un CSV/TXT contenant les liens, puis lancer :

```bash
uv run python scripts/ingest_source_archive.py chemin/vers/export.mbox
```

Le script accepte aussi un repertoire d'EML et les exports MBOX d'Apple Mail.
Il ne demande pas de recopier les caracteristiques des biens : un lien
d'alerte Jinka ou une URL de fiche suffit. Pour les emails Jinka recents, le
script peut suivre le bouton "Voir dans l'application Jinka" avec
`--resolve-tracked-links` afin de retrouver l'`alert_id` cache derriere
SendGrid. Ce suivi ne concerne pas le lien de desactivation.

Pour autoriser la collecte authentifiee des annonces visibles dans Jinka,
sauvegarder une session locale :

```bash
uv run python scripts/setup_jinka_session.py
```

Le fichier `data/jinka_storage_state.json` contient des cookies et reste ignore
par Git. Pour GitHub Actions, l'encoder en base64 et le stocker dans le secret
`JINKA_STORAGE_STATE_B64`. La collecte des alertes en attente peut ensuite etre
executee localement avec :

```bash
uv run python scripts/collect_jinka_alert_ads.py --limit 10
```

Le workflow `Sourcing immobilier` s'execute a 05:17 et 17:17 UTC. Il peut lire
une boite dediee en IMAP, sans marquer les messages comme lus, avec les secrets
GitHub `SOURCING_IMAP_HOST`, `SOURCING_IMAP_USERNAME` et
`SOURCING_IMAP_PASSWORD`. Les variables facultatives sont
`SOURCING_IMAP_PORT` (993), `SOURCING_IMAP_MAILBOX` (INBOX),
`SOURCING_IMAP_SENDER` et `SOURCING_IMAP_LOOKBACK_DAYS` (2). Si
`JINKA_STORAGE_STATE_B64` est defini, le workflow developpe aussi les alertes
Jinka en URLs avant de traiter la queue. Pour le chargement initial, declencher
manuellement le workflow avec 90 jours de recul.

Le quota gratuit Gemini peut limiter fortement le rythme de traitement. Par
defaut, l'agent espace les appels Gemini de 13 secondes et retente une fois les
erreurs temporaires de quota. Les variables `GEMINI_MIN_INTERVAL_SECONDS` et
`GEMINI_MAX_RETRIES` permettent d'ajuster ce comportement, par exemple avec un
quota payant ou un autre modele.

Si le quota reste atteint apres les tentatives configurees, le run de sourcing
s'arrete avec le statut `rate_limited` : l'URL en cours est remise en attente
et les URLs suivantes ne sont pas consommees inutilement. Il suffit alors de
relancer le workflow ou la commande locale plus tard.

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

## CLI CSV de compatibilite

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

# Plan d'implementation Phase 2

> Ce document decrit le durcissement du pipeline existant. La direction
> analytique courante est completee par l'ADR 002 : une cartographie de
> viabilite hors ligne doit desormais preceder le Monte Carlo propre a chaque
> annonce. Le sourcing approfondi n'a vocation a traiter que les opportunites
> preselectionnees par cette carte.

Ce plan transforme l'aspirateur d'annonces en pipeline automatisable sans
affaiblir la qualite des decisions financieres.

## Avancement courant

- [x] Profil stochastique explicite pour l'orchestrateur de sourcing.
- [x] Seed stable par URL pour reproduire les analyses.
- [x] Solveur inverse a prix unique, avec scenarios figes pendant la recherche.
- [x] Tables `extraction_runs` et `analysis_runs` pour sortir les diagnostics
  techniques du champ `notes`.
- [x] Sauvegarde des traces d'extraction et d'analyse depuis l'orchestrateur.
- [x] Politique de financement dynamique avec apport proportionnel et frais
  d'acquisition ajustes par le solveur.
- [x] File d'URLs et ingestion idempotente.
- [x] Prefiltre deterministe avant Playwright et LLM.
- [x] Blocages anti-bot et consent walls marques explicitement dans la queue.
- [x] Quota par source et par run pour limiter les chargements navigateur.
- [x] Resume persistant des runs de sourcing consultable dans Streamlit.
- [x] Workflow GitHub Actions planifie et declenchable manuellement.
- [x] Import idempotent des alertes Jinka depuis CSV, texte, EML, MBOX ou IMAP.
- [x] Stockage separe des `alert_id` Jinka avant developpement en URLs d'annonces.
- [x] Collecte authentifiee des alertes Jinka via session Playwright sauvegardee.
- [x] Canonicalisation des liens Jinka pour supprimer les identifiants d'alerte et de campagne.
- [x] Cockpit Streamlit minimal pour consulter les nouveaux runs.
- [x] Funnel decisionnel et priorites d'annonces dans Streamlit.
- [x] Preuves d'extraction et d'analyse mises en avant pour l'annonce active.
- [x] Relance manuelle d'analyse financiere depuis l'annonce active.
- [x] Deltas entre les deux derniers runs d'analyse d'une meme annonce.
- [x] Page Queue sourcing pour ajouter, editer, requeue, ignorer et traiter les URLs.

## Phase 2A - Fiabiliser l'analyse automatique

Objectif : produire des scores reproductibles et auditables avant toute
automatisation quotidienne.

- Remplacer les simulations pseudo-deterministes par un profil stochastique
  explicite pour le sourcing.
- Utiliser une seed stable par annonce afin de reproduire une analyse.
- Evaluer le prix cible sur un meme jeu de scenarios pour eviter le bruit Monte
  Carlo entre deux prix.
- Faire varier uniquement le prix dans le solveur inverse ; le loyer, les
  charges et les travaux restent constants, tandis que le financement suit une
  politique explicite.
- Persister ou afficher les diagnostics : seed, nombre de scenarios, statut du
  solveur, bornes de prix testees et raisons d'echec.

## Phase 2B - Durcir la persistance et les runs

Objectif : separer l'etat applicatif vivant des artefacts locaux.

- Utiliser PostgreSQL gratuit comme cible de production, SQLite restant le mode
  local/offline.
- Ajouter des tables dediees aux sources, observations, extractions et analyses.
- Stocker les versions de modeles, prompts, hypotheses, schema et fiscalite.
- Rendre l'ingestion idempotente par URL canonique et hash de contenu.
- Conserver les erreurs d'extraction au lieu de les perdre dans les logs CI.

## Phase 2C - Automatiser prudemment l'acquisition

Objectif : alimenter le pipeline sans construire un scraper fragile comme point
unique de defaillance.

- Commencer par une file d'URLs, alertes mail ou exports simples.
- Utiliser les emails Jinka comme declencheurs d'`alert_id`, puis une session
  Jinka authentifiee pour developper ces alertes en fiches `/ad/<uuid>`.
- Reserver le pipeline Playwright + LLM d'extraction aux fiches deja
  identifiees.
- Ajouter un prefiltre deterministe avant tout appel LLM.
- Marquer explicitement les blocages anti-bot et consent walls.
- Appliquer des quotas par source et par run.
- Lancer GitHub Actions sur un petit volume, avec resume de run et statut
  consultable dans Streamlit.

Configuration GitHub Actions recommandee :

- Secret `GEMINI_API_KEY` obligatoire pour traiter la queue.
- Secret `DATABASE_URL` recommande pour persister les runs hors du runner
  GitHub. Sans ce secret, SQLite reste possible mais ephemeral dans CI.
- Variable optionnelle `SOURCING_LIMIT`, par defaut `20`.
- Secrets optionnels `SOURCING_IMAP_HOST`, `SOURCING_IMAP_USERNAME` et
  `SOURCING_IMAP_PASSWORD` pour alimenter automatiquement la queue.
- Variables optionnelles `SOURCING_IMAP_PORT`, `SOURCING_IMAP_MAILBOX`,
  `SOURCING_IMAP_SENDER` et `SOURCING_IMAP_LOOKBACK_DAYS`.
- Secret optionnel `JINKA_STORAGE_STATE_B64` pour restaurer une session Jinka
  Playwright et transformer les alertes en URLs d'annonces dans CI.
- Variable optionnelle `JINKA_ALERT_LIMIT`, par defaut `10`.
- Variable optionnelle `SOURCING_SOURCE_LIMIT`, par defaut `20`.
- Variable optionnelle `SOURCING_ALLOWED_DOMAINS`, par defaut
  `jinka.fr,leboncoin.fr,seloger.com,bienici.com,pap.fr`.

## Phase 2D - Recentrer Streamlit en cockpit de decision

Objectif : faire de l'interface un outil d'audit et de decision, pas un moteur de
calcul de fond.

- Afficher un funnel : nouveau, extraction bloquee, donnees insuffisantes, hors
  criteres, a verifier, shortlist, contacte, offre faite, rejete.
- Mettre en avant les preuves extraites, champs manquants, red flags et
  hypothèses utilisees.
- Permettre une relance manuelle d'analyse sur une annonce selectionnee.
- Montrer les deltas entre runs quand les hypotheses ou donnees sources changent.

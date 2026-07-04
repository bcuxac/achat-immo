# Roadmap du Projet Achat Immo

Ce document trace l'avancement global de l'application et les prochaines étapes majeures de l'architecture.

## Phase 1 : Cœur Métier et Moteur Stochastique (Terminée ✅)
- [x] Extraction automatique des annonces (IA Gemini + Playwright).
- [x] Modèle de données (Stratégie, Hypothèses, Scénarios).
- [x] Moteur de simulation Monte Carlo (probabilités de succès, cashflow, TRI).
- [x] Solveur inversé multi-critères (Trouver le prix cible recommandable pour satisfaire TRI, CoC, et Cashflow).
- [x] Orchestrateur en tâche de fond (`run_orchestrator.py`).
- [x] Intégration à l'interface Streamlit (UI robuste, sauvegarde en base de données).

## Phase 2 : Cartographie de viabilite et prefiltrage (En cours)
L'objectif est de precalculer les zones de rentabilite par ville et profil
investisseur avant de soumettre les annonces prometteuses a l'orchestrateur.

- [x] Plan d'experiences Sobol pour les biens hypothetiques.
- [x] Scenarios economiques communs et qualification canonique.
- [ ] Artefact de carte indexe et interrogation d'une annonce.
- [ ] Validation du prefiltre face a un Monte Carlo complet.
- [ ] Integration dans l'orchestrateur avant l'analyse approfondie.

## Phase 3 : Acquisition massive et veille active
- [ ] Définir la source de découverte : alertes, exports ou pages de résultats.
- [ ] Extraire les donnees minimales sans appel LLM systematique.
- [ ] Utiliser la carte pour limiter les analyses approfondies.
- [ ] Notifications Telegram/Discord/Email des annonces identifiées comme "Coup de cœur" par le solveur inversé.
- [ ] Génération automatique du dossier de financement (PDF).

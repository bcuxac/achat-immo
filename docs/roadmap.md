# Roadmap du Projet Achat Immo

Ce document trace l'avancement global de l'application et les prochaines étapes majeures de l'architecture.

## Phase 1 : Cœur Métier et Moteur Stochastique (Terminée ✅)
- [x] Extraction automatique des annonces (IA Gemini + Playwright).
- [x] Modèle de données (Stratégie, Hypothèses, Scénarios).
- [x] Moteur de simulation Monte Carlo (probabilités de succès, cashflow, TRI).
- [x] Solveur inversé multi-critères (Trouver le prix cible recommandable pour satisfaire TRI, CoC, et Cashflow).
- [x] Orchestrateur en tâche de fond (`run_orchestrator.py`).
- [x] Intégration à l'interface Streamlit (UI robuste, sauvegarde en base de données).

## Phase 2 : Carte mathematique des simulations (Terminée ✅)
L'objectif est de precalculer les distributions financieres par ville et
entrees de simulation, sans qualification ni decision automatique.

- [x] Plan d'experiences Sobol pour les biens hypothetiques.
- [x] Scenarios economiques communs et metriques continues.
- [x] Artefact indexe et interpolation numerique d'une annonce.
- [x] Validation hors echantillon par erreur absolue.
- [x] Visualisations prix/m2-loyer/m2 et TRI-risque avec annonces superposees.
- [x] Integration non decisionnelle dans l'orchestrateur.

## Phase 3 : Acquisition massive et veille active
- [ ] Définir la source de découverte : alertes, exports ou pages de résultats.
- [ ] Extraire les donnees minimales sans appel LLM systematique.
- [ ] Utiliser les metriques de carte pour ordonner la file sans supprimer d'annonce.
- [ ] Notifications Telegram/Discord/Email des annonces identifiées comme "Coup de cœur" par le solveur inversé.
- [ ] Génération automatique du dossier de financement (PDF).

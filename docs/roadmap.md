# Roadmap du Projet Achat Immo

Ce document trace l'avancement global de l'application et les prochaines étapes majeures de l'architecture.

## Phase 1 : Cœur Métier et Moteur Stochastique (Terminée ✅)
- [x] Extraction automatique des annonces (IA Gemini + Playwright).
- [x] Modèle de données (Stratégie, Hypothèses, Scénarios).
- [x] Moteur de simulation Monte Carlo (probabilités de succès, cashflow, TRI).
- [x] Solveur inversé multi-critères (Trouver le prix cible recommandable pour satisfaire TRI, CoC, et Cashflow).
- [x] Orchestrateur en tâche de fond (`run_orchestrator.py`).
- [x] Intégration à l'interface Streamlit (UI robuste, sauvegarde en base de données).

## Phase 2 : Automatisation et Déploiement "Aspirateur à 0€" (À Faire ⏳)
L'objectif est d'avoir un "aspirateur" automatisé qui tourne sans intervention humaine, récupère de nouvelles annonces, passe l'orchestrateur et nourrit la base de données.

- [ ] **Définir la source de l'Aspirateur** : Lien de recherche globale Jinka, ou liste d'alertes e-mails, ou fichier d'URLs.
- [ ] **Automatisation CI/CD (GitHub Actions)** : Configurer un job (ex: CRON tous les matins) qui lance le script `run_orchestrator.py` sur les nouvelles annonces.
- [ ] **Persistance à 0€** : S'assurer que le stockage des annonces soit pérenne (soit via commit auto du fichier `sqlite` dans le dépôt privé, soit via une base Postgres gratuite distante type Neon/Supabase).

## Phase 3 : Notifications et Veille Active (Futures idées 💡)
- [ ] Notifications Telegram/Discord/Email des annonces identifiées comme "Coup de cœur" par le solveur inversé.
- [ ] Génération automatique du dossier de financement (PDF).

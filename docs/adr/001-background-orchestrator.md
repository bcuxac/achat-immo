# ADR 001 : Déplacement du Monte Carlo et Solveur Inversé vers l'Orchestrateur (Background)

## Contexte
Historiquement, la logique de calcul (simulation déterministe) et l'interface utilisateur étaient fortement couplées dans l'application web Streamlit.
Avec l'ajout du Sourcing IA (Scraping + Gemini) et du moteur stochastique (Monte Carlo + Solveur Inversé), se pose la question de *où* exécuter ces tâches.

Si le Monte Carlo est exécuté dans Streamlit à chaque chargement d'annonce :
- L'expérience utilisateur est ralentie.
- Le serveur d'hébergement web (Streamlit Cloud, Heroku) doit supporter des pics de charge CPU inutiles.
- L'investisseur doit analyser chaque annonce une par une pour connaître sa robustesse.

## Décision
Nous avons décidé d'adopter une **architecture asynchrone / hors-ligne pour la qualification des opportunités**.
Les moteurs d'Analyse Avancée (Monte Carlo, Solveur Inversé) seront déplacés dans la **Phase de Chasse** (Sourcing), exécutée par un "Orchestrateur" en tâche de fond (script CRON, Daemon ou Worker).

Le workflow formel devient le suivant :
1. **Acquisition** : Scraping de Jinka/BienIci.
2. **Extraction** : Gemini convertit le HTML brut en objet `CandidateProperty`.
3. **Risques** : Le `MonteCarloRunner` exécute 1000 scénarios sur ce candidat avec des hypothèses par défaut.
4. **Solveur** : L'`InverseSolver` détermine le *Prix Cible Maximum* recommandé pour atteindre un TRI cible.
5. **Persistance** : L'annonce est sauvegardée dans PostgreSQL avec ses KPIs pré-calculés (ex: `tri_p50`, `prix_cible`).

## Conséquences
### Positives
- **Interface ultra-rapide** : L'application Streamlit n'est plus qu'un "Dashboard de lecture" qui affiche des métriques pré-calculées. Faible consommation de ressources web.
- **Filtrage automatisé** : L'orchestrateur peut décider de ne même pas sauvegarder une annonce si le TRI P50 est inférieur à un seuil critique ou si le prix demandé nécessite une négociation de plus de 40%.
- **Passage à l'échelle** : On peut traiter 10 000 annonces la nuit, l'investisseur ne lira que le Top 10 le matin.

### Négatives / Contraintes
- **Modification du Schéma de Base de données** : Il faut étendre la table `annonces` pour stocker de nouveaux champs (les percentiles de risque, la probabilité de perte, le prix cible d'offre).
- **Perte de flexibilité "Directe"** : Si l'utilisateur change une hypothèse de base dans Streamlit (ex: taux de crédit général de 3% à 4%), les KPIs pré-calculés en base deviennent obsolètes.
  - *Mitigation* : Streamlit conservera la capacité de "Re-lancer un Monte Carlo en direct" à la demande pour l'annonce active.

## Statut
Adopté.

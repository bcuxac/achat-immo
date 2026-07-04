# Audit des choix de configuration

Ce document distingue les preferences utilisateur, les hypotheses de risque,
les heuristiques d'inference et les regles legales. Toutes les valeurs
numeriques ne doivent pas devenir des preferences modifiables.

## Configuration utilisateur centralisee

Le `InvestmentProfile` historise maintenant :

- ville cible ;
- budget total et apport ;
- duree, taux, assurance et source du taux ;
- horizon de detention et TMI ;
- regime fiscal de reference et gestion ;
- objectifs TRI, TRI P10, cash-on-cash, cash-flow et probabilite ;
- budgets de calcul Monte Carlo, solveur et cartographie ;
- distributions de loyer, vacance, inflation, appreciation, revente et travaux.

Ces valeurs sont modifiables dans `Parametres / Automatisation`. Chaque
enregistrement ajoute une version identifiee par un hash ; une analyse conserve
ce hash dans ses diagnostics.

## Heuristiques encore a traiter

| Emplacement | Valeurs | Traitement prevu |
|---|---|---|
| `sourcing_agents/orchestrator.py` | loyer, charges et taxe de repli au m2 | Remplacer par plages locales et qualification `a_enrichir` |
| Qualification d'une annonce | categorie reglementaire parfois absente | Tester toutes les categories plausibles puis demander l'enrichissement |
| `app/sections/financial_analysis.py` | variations compactes de prix et loyer | Conserver comme raccourcis UI, avec saisie libre avancee |
| `comparison.py` et `property_sheet.py` | seuils et poids de presentation historiques | Remplacer par la qualification canonique issue du profil |
| `hypothesis_inference.py` | estimations DPE, charges et travaux | Versionner comme politique d'inference, sans les presenter comme faits |
| workflow GitHub | quotas et domaines de sourcing | Rendre modifiables via configuration de deploiement synchronisee |

## Valeurs qui restent dans le modele

Les baremes fiscaux, regles de plus-value, compatibilites de regimes et plafonds
legaux de loyer ne sont pas des preferences. Ils restent dans des modules
versionnes, accompagnes de leurs sources et de tests. Une modification de ces
valeurs invalide les cartes de viabilite correspondantes.

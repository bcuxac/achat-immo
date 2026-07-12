# ADR 002 : Carte mathematique en amont de l'analyse approfondie

## Contexte

Le moteur fiscal et financier est deterministe : une meme combinaison de bien,
de financement, de fiscalite et de scenario produit le meme resultat. Executer
immediatement un Monte Carlo complet et un solveur inverse pour chaque annonce
est donc inutilement couteux lorsqu'il faut parcourir un grand volume de biens.

Le produit doit identifier les annonces ayant un fort potentiel de rentabilite,
sans confondre potentiel, robustesse et decision humaine. Une annonce incomplete
mais prometteuse ne doit pas etre rejetee uniquement parce que certaines donnees
ne sont pas encore disponibles.

## Decision

Une surface de simulation sera calculee hors ligne pour chaque combinaison
versionnee de :

- ville et regles locales ;
- profil investisseur et financement ;
- variantes locatives et fiscales ;
- hypotheses economiques ;

La surface explorera des biens hypothetiques au moyen d'un plan
d'experiences couvrant l'espace des parametres. Chaque bien hypothetique sera
evalue sous un ensemble commun de scenarios economiques afin de produire des
metriques comparables : TRI median et P10, cash-flow de premiere annee median et
P10, pire cash-flow annuel, cash-on-cash, VAN, probabilites de cash-flow positif
et distributions de tresorerie. Aucun prix maximal, seuil de rentabilite ou
verdict n'est calcule par la carte elle-meme.

Une annonce reelle est projetee dans cet espace. L'interpolation restitue des
estimations numeriques, un percentile et une distance aux points connus. Une
donnee manquante produit un avertissement et une estimation partielle, jamais un
rejet. Les seuils personnels restent dans l'analyse detaillee et dans les
filtres interactifs.

## Separation des responsabilites

Trois etats distincts seront conserves :

1. l'etat technique du traitement (queue, extraction, erreur, blocage) ;
2. les resultats financiers numeriques et leur precision d'interpolation ;
3. la decision humaine (shortlist, contact, offre, rejet, archive).

Les donnees manquantes ne seront jamais remplacees silencieusement par une
valeur supposee. Une plage d'exploration n'est utilisable que si elle est
explicitement enregistree comme hypothese du profil. Une contrainte legale non
verifiable, par exemple le loyer precedent en zone tendue sans grille locale,
declenche un avertissement d'enrichissement et non un verdict juridique.

## Consequences

- L'estimation preliminaire de milliers d'annonces devient une interrogation
  rapide d'un artefact calcule a l'avance.
- Les cartes doivent etre invalidees et regenerees lorsque leur configuration,
  les regles fiscales ou les regles locales changent.
- La couverture de l'espace et les erreurs absolues d'interpolation doivent etre
  mesurees face a des simulations completes hors echantillon.
- Le pipeline de sourcing reste necessaire pour l'acquisition, l'extraction,
  l'enrichissement, la tracabilite et la decision.

## Statut

Adopte.

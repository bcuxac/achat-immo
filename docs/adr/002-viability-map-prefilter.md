# ADR 002 : Cartographie de viabilite en amont du sourcing approfondi

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

Une cartographie de viabilite sera calculee hors ligne pour chaque combinaison
versionnee de :

- ville et regles locales ;
- profil investisseur et financement ;
- variantes locatives et fiscales ;
- hypotheses economiques ;
- objectifs de rentabilite.

La cartographie explorera des biens hypothetiques au moyen d'un plan
d'experiences couvrant l'espace des parametres. Chaque bien hypothetique sera
evalue sous un ensemble commun de scenarios economiques afin de produire des
metriques comparables : TRI median et P10, cash-flow de premiere annee median et
P10, pire cash-flow annuel, cash-on-cash, VAN, probabilites de cash-flow positif
et prix maximal compatible avec les objectifs.

La qualification economique d'un point distingue :

- `rentable_et_autofinance` lorsque les objectifs de rendement et de tresorerie sont atteints ;
- `rentable_cashflow_initial_positif` lorsque la premiere annee est robuste mais pas tout l'horizon ;
- `rentable_avec_effort_epargne` lorsque les objectifs de TRI sont atteints mais pas ceux de tresorerie ;
- `rentabilite_fragile` lorsque le TRI median atteint la cible mais pas son P10 ;
- `sous_objectif_rentabilite` lorsque le TRI median reste sous la cible.

Une annonce reelle sera d'abord projetee dans cette cartographie. Le resultat de
cette interrogation determinera si elle est :

- `robustement_viable` ;
- `potentiellement_viable` ;
- `a_enrichir` ;
- `non_viable` ;
- `bloquee`.

Les analyses couteuses propres au bien, notamment le Monte Carlo detaille et le
solveur inverse, seront reservees aux annonces robustement ou potentiellement
viables. Une relance humaine pourra toujours forcer l'analyse approfondie.

## Separation des responsabilites

Trois etats distincts seront conserves :

1. l'etat technique du traitement (queue, extraction, erreur, blocage) ;
2. la qualification financiere automatique ;
3. la decision humaine (shortlist, contact, offre, rejet, archive).

Les donnees manquantes ne seront jamais remplacees silencieusement par une
valeur supposee. Une plage d'exploration n'est utilisable que si elle est
explicitement enregistree comme hypothese du profil. Une contrainte legale non
verifiable, par exemple le loyer precedent en zone tendue sans grille locale,
declenche un enrichissement et non un verdict juridique.

## Consequences

- Le prefiltrage de milliers d'annonces devient une interrogation rapide d'un
  artefact calcule a l'avance.
- Les cartes doivent etre invalidees et regenerees lorsque leur configuration,
  les regles fiscales ou les regles locales changent.
- La couverture de l'espace et le taux de faux negatifs doivent etre mesures
  face a des analyses completes hors echantillon.
- Le pipeline de sourcing reste necessaire pour l'acquisition, l'extraction,
  l'enrichissement, la tracabilite et la decision.

## Statut

Adopte.

# Roadmap

L'objectif prioritaire est d'identifier automatiquement, dans un grand volume
d'annonces, les biens ayant un potentiel eleve de rentabilite ajustee du risque.

## Lot 1 - Doctrine et socle de cartographie

- [x] Formaliser la cartographie de viabilite comme prefiltre analytique.
- [x] Unifier les seuils TRI, TRI P10, cash-on-cash, cash-flow et probabilite.
- [x] Creer un plan d'experiences Sobol reproductible.
- [x] Evaluer les biens hypothetiques sous des chocs economiques communs.
- [x] Mesurer le rappel sur un echantillon hors carte.
- [ ] Raffiner adaptativement les frontieres et optimiser le cout de calcul.

## Lot 2 - Qualification rapide d'une annonce

- [x] Versionner et charger les artefacts de cartographie.
- [x] Projeter une annonce complete dans la carte.
- [x] Interroger une annonce partielle sans inventer les donnees absentes.
- [x] Produire des sorties numeriques continues et une distance d'interpolation.

## Lot 3 - Integration du pipeline

- [x] Persister les estimations numeriques associees aux annonces.
- [x] Reserver Monte Carlo et solveur aux annonces preselectionnees.
- [x] Afficher potentiel, confiance et raisons dans Streamlit.
- [x] Valider le taux de faux negatifs face aux analyses completes.

## Lot 4 - Acquisition et extension

- [ ] Brancher une source de decouverte a grand volume.
- [ ] Extraire les donnees minimales sans LLM lorsque possible.
- [ ] Etendre la cartographie aux autres segments de Grenoble puis a Nimes.

## Evolutions non prioritaires

- Modelisation des societes a l'IS.
- Dispositifs de defiscalisation specifiques.

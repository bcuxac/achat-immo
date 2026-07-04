# Roadmap

L'objectif prioritaire est d'identifier automatiquement, dans un grand volume
d'annonces, les biens ayant un potentiel eleve de rentabilite ajustee du risque.

## Lot 1 - Doctrine et socle de cartographie

- [x] Formaliser la cartographie de viabilite comme prefiltre analytique.
- [x] Unifier les seuils TRI, TRI P10, cash-on-cash, cash-flow et probabilite.
- [x] Creer un plan d'experiences Sobol reproductible.
- [x] Evaluer les biens hypothetiques sous des chocs economiques communs.
- [ ] Mesurer la convergence et raffiner les frontieres.

## Lot 2 - Qualification rapide d'une annonce

- [ ] Versionner et charger les artefacts de cartographie.
- [ ] Projeter une annonce complete dans la carte.
- [ ] Interroger des plages plausibles lorsque des donnees manquent.
- [ ] Produire une qualification explicable et une distance a la frontiere.

## Lot 3 - Integration du pipeline

- [ ] Persister les runs de qualification rapide.
- [ ] Reserver Monte Carlo et solveur aux annonces preselectionnees.
- [ ] Afficher potentiel, confiance et raisons dans Streamlit.
- [ ] Valider le taux de faux negatifs face aux analyses completes.

## Lot 4 - Acquisition et extension

- [ ] Brancher une source de decouverte a grand volume.
- [ ] Extraire les donnees minimales sans LLM lorsque possible.
- [ ] Etendre la cartographie aux autres segments de Grenoble puis a Nimes.

## Evolutions non prioritaires

- Modelisation des societes a l'IS.
- Dispositifs de defiscalisation specifiques.

Pour gerer les environnements et les executions, utilise toujours `uv`.

Je travaille sous Mac avec iCloud synchronise. La convention d'environnement Python de ce depot est stricte :

- Le virtualenv reel doit etre `./.venv.nosync/`.
- `./.venv` doit toujours etre un lien symbolique vers `./.venv.nosync`.
- Ne cree jamais `.venv2`, `.venv3` ou tout autre suffixe de contournement.
- Si `./.venv` existe mais n'est pas un symlink valide vers `./.venv.nosync`, considere l'environnement comme invalide au lieu d'en creer un autre.
- Si l'environnement est invalide ou absent, recree-le explicitement avec `uv` en restaurant cette structure, puis reutilise `./.venv`.
- N'utilise pas `python -m venv`, `virtualenv`, Poetry ou un autre gestionnaire pour creer un environnement local dans ce depot, sauf demande explicite.
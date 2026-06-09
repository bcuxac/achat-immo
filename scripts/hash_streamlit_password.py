"""Genere un hash de mot de passe pour les secrets Streamlit."""

from __future__ import annotations

from getpass import getpass
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from achat_immo.auth import hash_password


def main() -> None:
    password = getpass("Mot de passe a hasher: ")
    confirmation = getpass("Confirmation: ")
    if password != confirmation:
        raise SystemExit("Les deux saisies ne correspondent pas.")
    print(hash_password(password))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Ouvre Jinka pour sauvegarder une session authentifiee Playwright."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from achat_immo.jinka_collect import DEFAULT_JINKA_STORAGE_STATE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sauvegarder une session Jinka authentifiee.")
    parser.add_argument(
        "--storage-state",
        type=Path,
        default=DEFAULT_JINKA_STORAGE_STATE,
        help="Fichier Playwright storage_state a creer.",
    )
    parser.add_argument(
        "--start-url",
        default="https://www.jinka.fr/sign/in",
        help="URL ouverte pour se connecter a Jinka.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    load_dotenv()
    args.storage_state.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(args.start_url, wait_until="domcontentloaded")
        print("Connecte-toi a Jinka dans la fenetre Chromium ouverte.")
        print("Quand la page Jinka authentifiee est visible, reviens ici et appuie sur Entree.")
        input()
        context.storage_state(path=str(args.storage_state))
        context.close()
        browser.close()
    print(f"Session Jinka sauvegardee dans {args.storage_state}.")


if __name__ == "__main__":
    main()

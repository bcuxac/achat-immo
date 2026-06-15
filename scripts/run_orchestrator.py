#!/usr/bin/env python3
"""Script CLI pour exécuter l'Orchestrateur de Sourcing."""

import argparse
import logging
from dotenv import load_dotenv

from achat_immo.storage import open_database
from achat_immo.sourcing_agents.orchestrator import SourcingOrchestrator

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Orchestrateur de Sourcing Immobilier")
    parser.add_argument("url", type=str, help="L'URL de l'annonce à analyser (Jinka, Leboncoin, etc.)")
    parser.add_argument("--tri", type=float, default=6.0, help="TRI cible minimum (%)")
    parser.add_argument("--coc", type=float, default=0.0, help="Cash-on-Cash cible minimum (%)")
    parser.add_argument("--cf", type=float, default=0.0, help="Cashflow mensuel cible minimum (€)")
    
    args = parser.parse_args()
    
    load_dotenv()
    
    logger.info(f"Démarrage de l'orchestrateur. Cibles: TRI={args.tri}%, CoC={args.coc}%, CF={args.cf}€")
    
    orchestrator = SourcingOrchestrator(
        target_tri=args.tri,
        target_coc=args.coc,
        target_cf=args.cf
    )
    
    conn = open_database()
    try:
        annonce_id = orchestrator.process_url(conn, args.url)
        logger.info(f"Annonce sauvegardée avec succès ! ID: {annonce_id}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()

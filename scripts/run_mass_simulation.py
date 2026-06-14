#!/usr/bin/env python
"""Lance une simulation de masse avec une belle interface et exporte les resultats."""

import argparse
import datetime
import json
import os
import sys

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

# Permettre l'import depuis src/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from achat_immo.mass_simulation import executer_simulation_masse

def main() -> None:
    parser = argparse.ArgumentParser(description="Simulation de Masse d'investissements immobiliers.")
    parser.add_argument("--nb", type=int, default=10000, help="Nombre de biens a simuler (defaut: 10000)")
    parser.add_argument("--workers", type=int, default=4, help="Nombre de threads (defaut: 4)")
    args = parser.parse_args()

    console = Console()
    console.rule("[bold blue]Lancement Simulation de Masse[/bold blue]")
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    params = {
        "nb_simulations": args.nb,
        "workers": args.workers,
        "surface_min": 15.0,
        "surface_max": 60.0,
        "prix_m2_min": 1500.0,
        "prix_m2_max": 6000.0,
        "loyer_m2_min": 10.0,
        "loyer_m2_max": 30.0,
        "travaux_pct_min": 0.0,
        "travaux_pct_max": 30.0,
    }
    
    params_file = f"params_mass_sim_{timestamp}.json"
    with open(params_file, "w") as f:
        json.dump(params, f, indent=4)
        
    console.print(f"Paramètres sauvegardés dans : [bold green]{params_file}[/bold green]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task(f"Simulation de {args.nb} biens en cours...", total=None)
        df = executer_simulation_masse(**params)
        progress.update(task, completed=True)

    csv_file = f"resultats_mass_sim_{timestamp}.csv"
    df.to_csv(csv_file, index=False)
    console.print(f"Résultats bruts exportés vers : [bold green]{csv_file}[/bold green] ({len(df)} lignes)")
    
    # Analyze the Pépites
    console.rule("[bold gold1]Analyse des Pépites (Golden Rules)[/bold gold1]")
    
    pepites = df[(df["tri_annuel_pct"] >= 10.0) & (df["effort_epargne_mensuel"] >= 0.0)]
    
    if len(pepites) == 0:
        console.print("[bold red]Aucune pépite trouvée avec ces critères ![/bold red]")
        return
        
    console.print(f"Sur {len(df)} scénarios, [bold green]{len(pepites)}[/bold green] sont des pépites (TRI >= 10%, CashFlow >= 0).")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Métrique")
    table.add_column("Moyenne")
    table.add_column("Min (P0)")
    table.add_column("Max (P100)")
    table.add_column("Médiane (P50)")
    
    metrics = {
        "Prix/m2 (€)": "prix_m2",
        "Loyer/m2 (€)": "loyer_m2",
        "Rendement Brut (%)": "rendement_brut_pct",
        "Travaux (%)": "travaux_pct",
        "Taux Crédit (%)": "taux_credit_pct",
        "Taxe Foncière (mois)": "tf_mois",
        "TRI (%)": "tri_annuel_pct",
    }
    
    for label, col in metrics.items():
        if col in pepites.columns:
            mean_val = pepites[col].mean()
            p0 = pepites[col].min()
            p100 = pepites[col].max()
            p50 = pepites[col].median()
            
            if "pct" in col or "%" in label:
                if col == "travaux_pct":
                    fmt = lambda x: f"{x*100:.1f}%"
                else:
                    fmt = lambda x: f"{x:.1f}%"
            else:
                fmt = lambda x: f"{x:.1f}"
                
            table.add_row(label, fmt(mean_val), fmt(p0), fmt(p100), fmt(p50))
            
    console.print(table)
    
    console.print("\n[bold]Répartition par régime fiscal gagnant :[/bold]")
    regimes = pepites["regime_fiscal"].value_counts()
    for regime, count in regimes.items():
        console.print(f"- {regime}: {count} pépites ({count/len(pepites)*100:.1f}%)")

if __name__ == "__main__":
    main()

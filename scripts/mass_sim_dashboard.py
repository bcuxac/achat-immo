"""Application Streamlit pour visualiser les resultats de la simulation de masse."""

import os
import glob
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Pépites Immo - Dashboard", layout="wide")

st.title("🏡 Explorateur de Pépites Immobilières")
st.markdown("Visualisation dynamique des frontières de rentabilité issues de la simulation Deep Monte Carlo.")

@st.cache_data
def load_data(file_path: str) -> pd.DataFrame:
    return pd.read_csv(file_path)

# Trouver tous les fichiers csv de resultat dans le rep parent ou courant
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
csv_files = glob.glob(os.path.join(base_dir, "resultats_mass_sim_*.csv"))

if not csv_files:
    st.warning("Aucun fichier de résultat trouvé. Lancez d'abord la simulation de masse via le terminal (`uv run scripts/run_mass_simulation.py --nb 100`).")
    st.stop()

# Trier par le plus recent
csv_files.sort(reverse=True)
selected_file_name = st.sidebar.selectbox("Sélectionnez le fichier de simulation", [os.path.basename(f) for f in csv_files])
selected_file = os.path.join(base_dir, selected_file_name)

df = load_data(selected_file)

# Sidebar pour filtrer ce qui definit une pepite
st.sidebar.header("🎯 Définition de la Pépite")
tri_cible = st.sidebar.slider("TRI Minimum (%)", 0.0, 30.0, 10.0, 0.5)
cf_cible = st.sidebar.number_input("CashFlow Minimum Mensuel (€)", value=0.0, step=50.0)

# Filtrer
df["est_pepite"] = (df["tri_annuel_pct"] >= tri_cible) & (df["effort_epargne_mensuel"] >= cf_cible)
pepites = df[df["est_pepite"]]

st.header(f"📈 Résultats : {len(pepites)} Pépites sur {len(df)} scénarios ({len(pepites)/len(df)*100:.1f}%)")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Frontière de Prix/Loyer")
    fig1 = px.scatter(
        df, x="prix_m2", y="loyer_m2", 
        color="est_pepite", 
        color_discrete_map={True: "#00cc66", False: "#ff4d4d"},
        opacity=0.6,
        title="Quel Loyer pour quel Prix/m2 ?",
        labels={"prix_m2": "Prix/m² (€)", "loyer_m2": "Loyer/m² (€)"}
    )
    st.plotly_chart(fig1, use_container_width=True)

with col2:
    st.subheader("Frontière de Taux/Rendement Brut")
    fig2 = px.scatter(
        df, x="taux_credit_pct", y="rendement_brut_pct", 
        color="est_pepite", 
        color_discrete_map={True: "#00cc66", False: "#ff4d4d"},
        opacity=0.6,
        title="Quel rendement brut viser selon le taux de crédit ?",
        labels={"taux_credit_pct": "Taux Crédit (%)", "rendement_brut_pct": "Rendement Brut (%)"}
    )
    st.plotly_chart(fig2, use_container_width=True)

st.header("🔍 Statistiques des Pépites (Vos Filtres à appliquer)")
if not pepites.empty:
    stats_df = pepites[["prix_m2", "loyer_m2", "rendement_brut_pct", "travaux_pct", "tf_mois", "taux_credit_pct", "tri_annuel_pct"]].describe().T
    stats_df = stats_df[["mean", "min", "25%", "50%", "75%", "max"]]
    stats_df.columns = ["Moyenne", "Minimum (P0)", "1er Quartile", "Médiane", "3eme Quartile", "Maximum (P100)"]
    st.dataframe(stats_df.style.format("{:.2f}"), use_container_width=True)
    
    st.subheader("Régime Fiscal Gagnant")
    regime_counts = pepites["regime_fiscal"].value_counts().reset_index()
    regime_counts.columns = ["Régime", "Nombre"]
    fig3 = px.pie(regime_counts, names="Régime", values="Nombre", hole=0.4, title="Meilleur montage fiscal pour les pépites")
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.warning("Aucune pépite ne correspond à ces critères.")

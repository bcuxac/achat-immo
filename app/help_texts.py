"""Textes d'aide affiches par l'interface Streamlit."""

from __future__ import annotations


HYPOTHESES_HELP = {
    "frais_notaire_estimes": (
        "Impact fort sur le cout total et le pret. Estimation automatique : environ 8 % dans l'ancien, "
        "2,5 % si l'annonce mentionne neuf ou VEFA. A remplacer par le decompte notarial."
    ),
    "frais_agence_achat": (
        "Impact fort si les honoraires sont a charge acquereur. Laisser a 0 si le prix est FAI ou si les "
        "honoraires sont a charge vendeur."
    ),
    "travaux_estimes": (
        "Impact tres fort : augmente le cout total mais peut aussi reduire le resultat fiscal au reel. "
        "Inclure travaux immediats, energetiques, remise en location et marge d'imprevu."
    ),
    "meubles_estimes": (
        "Budget mobilier du scenario meuble. Il reste saisi meme si le regime de reference est nu : "
        "le moteur le neutralise automatiquement pour les strategies en location nue."
    ),
    "frais_bancaires": (
        "Frais de dossier, courtage eventuel et petits frais de mise en place du pret. Impact modere mais finance."
    ),
    "garantie": (
        "Cautionnement, credit logement ou garantie bancaire. Impacte le cout total finance ; a remplacer par "
        "l'offre bancaire des qu'elle existe."
    ),
    "mode_location": (
        "Determine le cadre fiscal et parfois le plafond de loyer. Meuble : revenus BIC/LMNP, CFE possible. "
        "Nue : revenus fonciers."
    ),
    "loyer_hc_mensuel": (
        "Loyer hors charges de reference. Il sert a pre-remplir la grille ; a Grenoble il doit rester sous le "
        "loyer de reference majore calcule. Source Grenoble : "
        "https://www.grenoblealpesmetropole.fr/940-me-renseigner-sur-l-encadrement-des-loyers.htm"
    ),
    "taxe_fonciere": (
        "Charge proprietaire recurrente, non incluse dans les charges locatives. Impact direct sur cash-flow "
        "et rendement net."
    ),
    "charges_copro_annuelles": (
        "Charges annuelles totales de copropriete payees par le proprietaire. Le modele retranche ensuite la "
        "part recuperable pour calculer la charge bailleur nette."
    ),
    "charges_recuperables_annuelles": (
        "Part des charges de copro refacturable au locataire. Ne doit pas depasser les charges copro annuelles."
    ),
    "assurance_pno": (
        "Assurance proprietaire non occupant. Charge recurrente deductible au reel, impact modere mais quasi "
        "systematique."
    ),
    "assurance_gli": (
        "Garantie loyers impayes. Si elle est activee, saisir le cout annuel ; ordre de grandeur courant : "
        "2,5 a 4 % des loyers charges comprises."
    ),
    "cfe_annuelle": (
        "Cotisation fonciere des entreprises. Les locations meublees peuvent y etre soumises, meme en LMNP ; "
        "exoneration generale si recettes <= 5 000 EUR. Source : "
        "https://www.impots.gouv.fr/particulier/questions/je-fais-de-la-location-meublee-dois-je-payer-de-la-cfe-cotisation-fonciere-des"
    ),
    "comptable_lmnp": (
        "Honoraires annuels d'expert-comptable ou plateforme comptable. Pertinent surtout en LMNP reel, car le "
        "regime reel suppose une comptabilite et une declaration de resultat. Source : "
        "https://www.impots.gouv.fr/particulier/les-regimes-dimposition"
    ),
    "entretien_annuel": (
        "Reserve annuelle pour petit entretien, remplacement et menus travaux non planifies. Impact direct sur "
        "cash-flow prudent."
    ),
    "gestion_agence_possible": (
        "Autorise la grille a tester les scenarios avec agence. Si decoche, les scenarios agence sont exclus."
    ),
    "regime_fiscal": (
        "Regime fiscal de reference pour l'annonce. La simulation peut ensuite tester automatiquement les "
        "regimes compatibles. Source : https://www.impots.gouv.fr/particulier/les-regimes-dimposition"
    ),
    "tmi_pct": (
        "Tranche marginale d'imposition du foyer. Le modele applique TMI + prelevements sociaux au resultat "
        "taxable positif ; c'est une approximation prudente."
    ),
    "prelevements_sociaux_pct": (
        "Taux 2026 sur revenu net locatif : 17,2 % en location nue, 18,6 % en location meublee. Source : "
        "https://www.impots.gouv.fr/particulier/questions/je-donne-un-bien-en-location-dois-je-payer-des-prelevements-sociaux"
    ),
    "part_terrain_pct": (
        "Part du prix correspondant au terrain, non amortissable en LMNP reel. Valeur indicative a confirmer "
        "avec le comptable."
    ),
    "duree_amortissement_bien_annees": (
        "Duree d'amortissement indicative du bati en LMNP reel. L'amortissement ne peut pas creer de deficit "
        "fiscal LMNP. Source : https://www.impots.gouv.fr/particulier/les-regimes-dimposition"
    ),
    "duree_amortissement_travaux_annees": (
        "Duree indicative d'amortissement des travaux immobilises au LMNP reel. A ajuster selon la nature des "
        "travaux et le comptable."
    ),
    "duree_amortissement_meubles_annees": (
        "Duree indicative d'amortissement du mobilier au LMNP reel. A ajuster selon le plan comptable retenu."
    ),
    "abattement_micro_bic_pct": (
        "Abattement forfaitaire micro-BIC pour location meublee longue duree : 50 % dans le cas usuel modelise. "
        "Les charges reelles ne sont alors pas deduites. Source : https://www.impots.gouv.fr/particulier/les-regimes-dimposition"
    ),
    "abattement_micro_foncier_pct": (
        "Abattement forfaitaire micro-foncier : 30 % si revenus fonciers bruts du foyer <= 15 000 EUR et pas "
        "d'exclusion. Source : https://bofip.impots.gouv.fr/bofip/3973-PGP.html"
    ),
}

FIELD_HELP = HYPOTHESES_HELP

SIMULATION_HELP = {
    "prix_decotes": (
        "Teste le prix affiche et les decotes de negociation. A modifier si la marge de negociation est "
        "manifestement plus faible ou plus forte."
    ),
    "loyer_variations": (
        "Teste un loyer prudent, central et optimiste autour du loyer de reference. Le plafond local reste applique."
    ),
    "taux_credit": "Taux annuels a comparer. Garde une fourchette courte pour lire rapidement l'effet bancaire.",
    "durees": "Durees de credit proposees. Elles pilotent fortement le cash-flow et le patrimoine net.",
    "apports": "Fonds propres investis au depart. Sert au TRI fonds propres et au cash-on-cash.",
    "assurance_emprunteur": "Taux annuel d'assurance emprunteur applique au capital initial.",
    "vacances": "Vacance locative annuelle testee. Un mois par an correspond a environ 8,33 % de vacance.",
    "modes_gestion": "Compare gestion directe et agence si l'annonce peut rester viable avec delegation.",
    "frais_gestion": "Honoraires annuels d'agence en pourcentage des loyers encaisses.",
    "comparer_regimes": "Teste automatiquement les regimes fiscaux compatibles avec le mode de location retenu.",
    "comparer_modes": "Ajoute la comparaison meublee / nue. Utile si la strategie n'est pas encore tranchee.",
    "regimes_fiscaux": "Permet d'exclure un regime que tu ne souhaites pas utiliser malgre sa compatibilite.",
    "horizon": "Duree de detention analysee. Elle change le TRI, la plus-value et le capital restant du.",
    "taux_actualisation": "Cout du capital utilise pour la VAN. 4 % est une valeur prudente par defaut.",
    "commentaire": "Libelle du snapshot sauvegarde pour retrouver l'hypothese de travail.",
    "grille_avancee": "Active les min/max/pas historiques si tu veux une grille plus large que le mode compact.",
}

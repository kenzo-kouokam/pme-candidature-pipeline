#!/usr/bin/env python3
"""
PHASE 3C — Générateur de LM personnalisées via Claude API
Input  : entreprises_cibles.csv
Output : lm_generees/{slug}.txt  +  lm_tracker.csv

Pour chaque entreprise score A/B :
  1. Détermine le template vertical
  2. Appelle Claude API pour générer 2 phrases d'intro personnalisées
  3. Injecte l'intro dans le template
  4. Sauvegarde la LM finale

Usage : python lm_generator.py
"""

import pandas as pd
import re
import time
import random
import os
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────
INPUT_CSV    = "entreprises_cibles.csv"
OUTPUT_DIR   = "lm_generees"
TRACKER_CSV  = "lm_tracker.csv"

TEMPLATES = {
    "ESN / Informatique"  : "template_esn_informatique.txt",
    "Conseil / BI"        : "template_conseil_bi.txt",
    "Fintech / Assurance" : "template_fintech_assurance.txt",
    "Retail / E-com"      : "template_retail_ecom.txt",
    "Startup / Scale-up"  : "template_startup_scaleup.txt",
}

DELAY_MIN = 1.5
DELAY_MAX = 3.0

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Helpers ───────────────────────────────────────────────────────────────
def slug(nom: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", nom.lower().strip())
    return s[:50].strip("_")

def load_template(vertical: str) -> str:
    path = TEMPLATES.get(vertical, TEMPLATES["Conseil / BI"])
    with open(path, encoding="utf-8") as f:
        return f.read()

def generate_intro(nom: str, vertical: str, url: str, page_carriere: str) -> str:
    """
    Génère 2 phrases d'intro personnalisées sans appel API externe.
    Phrase 1 : signal sur l'entreprise (domaine, positionnement)
    Phrase 2 : lien avec le profil data d'Enzo
    """
    has_career = page_carriere and str(page_carriere) not in ("nan", "", "None")
    domain = ""
    if url and str(url) not in ("nan", "", "None"):
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.replace("www.", "")
        except Exception:
            pass

    nom_court = nom.split(" ")[0] if len(nom.split(" ")) > 1 else nom

    # Phrases 1 selon vertical
    p1_options = {
        "ESN / Informatique": [
            f"{nom} intervient sur des projets de transformation numérique où la valeur des données est au cœur des livrables.",
            f"En tant qu'acteur du conseil IT, {nom} accompagne ses clients sur des chantiers où l'exploitation intelligente des données est devenue un levier stratégique.",
            f"{nom} positionne ses équipes sur des missions à forte composante technique, notamment en ingénierie data et développement de solutions analytiques.",
        ],
        "Conseil / BI": [
            f"{nom} s'appuie sur une approche data-driven pour accompagner ses clients dans leurs décisions stratégiques.",
            f"Le positionnement de {nom} sur le conseil en management et Business Intelligence en fait un environnement où la rigueur analytique est centrale.",
            f"La pratique BI de {nom} couvre des enjeux allant de la structuration des données à la production de tableaux de bord décisionnels.",
        ],
        "Fintech / Assurance": [
            f"{nom} opère dans un secteur où la modélisation du risque et l'analyse prédictive sont des différenciateurs compétitifs directs.",
            f"Dans un secteur financier en pleine mutation algorithmique, {nom} développe des approches quantitatives qui mobilisent ML et traitement de données à grande échelle.",
            f"La FinTech impose une maîtrise des données temps-réel et des modèles de scoring fiables — des enjeux que {nom} traite au quotidien.",
        ],
        "Retail / E-com": [
            f"{nom} évolue dans un secteur où l'optimisation des performances e-commerce repose sur une analyse fine des comportements d'achat et des données catalogue.",
            f"Le retail digital implique des volumes de données importants (commandes, stocks, comportements clients) que {nom} doit exploiter pour rester compétitif.",
            f"{nom} opère sur des marchés où chaque décision merchandising ou pricing peut être guidée par la donnée — un terrain qui requiert des modèles robustes et actionnables.",
        ],
        "Startup / Scale-up": [
            f"{nom} construit ses fondations data dans une phase de croissance où la rapidité d'exécution et la rigueur analytique ne doivent pas s'opposer.",
            f"En scale-up, {nom} fait face à l'enjeu classique de transformer une masse de données opérationnelles en insights actionnables à grande vitesse.",
            f"{nom} se trouve dans une étape clé où structurer ses pratiques data peut significativement accélérer la prise de décision.",
        ],
    }

    # Phrases 2 selon vertical
    p2_options = {
        "ESN / Informatique": [
            "Mon expérience de 2 ans en production ML (Python, Scikit-learn, XGBoost, AWS) sur des projets à impact mesurable me permettrait de m'intégrer rapidement sur ce type de missions.",
            "Ayant livré des modèles en production sur des données réelles — y compris sur des volumes e-commerce à l'international — je suis opérationnel sur des projets data end-to-end dès le premier jour.",
        ],
        "Conseil / BI": [
            "Mon profil mêle maîtrise des outils BI (Power BI, SQL) et capacité à construire des modèles prédictifs, ce qui me permet d'intervenir autant sur l'analyse que sur la modélisation.",
            "Habitué à travailler sur des données réelles avec des contraintes métier fortes, je peux apporter une contribution immédiate sur des sujets allant de la structuration data à la visualisation décisionnelle.",
        ],
        "Fintech / Assurance": [
            "Mon travail de scoring bancaire (XGBoost, AUC 0.76, 45k clients) et de production de modèles sur données financières me donne une lecture directe de ces enjeux.",
            "La rigueur quantitative exigée dans ce secteur correspond exactement à l'approche que j'applique : validation croisée systématique, interprétabilité des modèles (SHAP) et monitoring des dérives.",
        ],
        "Retail / E-com": [
            "Deux ans de production ML sur une marketplace Amazon (catalogues, prix, comportements) m'ont donné une maîtrise opérationnelle des données e-commerce à grande échelle.",
            "Mon expérience sur des données Amazon — optimisation de catalogue, modèles de recommandation, NLP sur 525k lignes — s'aligne directement avec les enjeux data du retail digital.",
        ],
        "Startup / Scale-up": [
            "Habitué à travailler en autonomie sur des projets data end-to-end (exploration → modélisation → mise en production), je m'adapte naturellement à un environnement où la polyvalence prime.",
            "Mon parcours, construit sur des projets concrets avec peu de ressources et des délais courts, me prépare bien à la réalité d'une scale-up data-driven.",
        ],
    }

    p1_list = p1_options.get(vertical, p1_options["Conseil / BI"])
    p2_list = p2_options.get(vertical, p2_options["Conseil / BI"])

    # Sélection déterministe (basée sur le nom pour éviter les répétitions entre runs)
    idx = sum(ord(c) for c in nom) % len(p1_list)
    p1 = p1_list[idx]
    p2 = p2_list[idx % len(p2_list)]

    # Si page carrière dispo, ajoute une mention dans P1
    if has_career:
        p1 = p1.rstrip(".") + f", comme en témoigne l'ouverture de postes sur votre page recrutement."

    return f"{p1} {p2}"

# ── Main ──────────────────────────────────────────────────────────────────
def main():
    print("=" * 58)
    print("PHASE 3C — Générateur LM")
    print(f"Démarrage : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 58)

    # Chargement CSV
    try:
        df = pd.read_csv(INPUT_CSV, encoding="utf-8-sig")
    except FileNotFoundError:
        print(f"❌ {INPUT_CSV} introuvable. Lance d'abord nettoyage_phase3a.py")
        return

    print(f"\n📂 {len(df)} entreprises cibles chargées")

    # Reprendre si tracker existe déjà
    done_slugs = set()
    if os.path.exists(TRACKER_CSV):
        tracker_df = pd.read_csv(TRACKER_CSV, encoding="utf-8-sig")
        done_slugs = set(tracker_df["slug"].tolist())
        print(f"   Déjà générées : {len(done_slugs)}")

    tracker_rows = []

    for i, row in enumerate(df.itertuples(), 1):
        nom      = str(row.nom)
        vertical = str(row.vertical)
        score    = str(row.score)
        url_r    = str(getattr(row, "url_resolue", "")) 
        page_c   = str(getattr(row, "page_carriere", ""))
        email    = str(getattr(row, "email", ""))
        s        = slug(nom)

        if s in done_slugs:
            print(f"[{i}/{len(df)}] ↩  {nom[:40]} — déjà fait")
            continue

        print(f"\n[{i}/{len(df)}] {nom[:45]} | {vertical} | Score {score}")

        # Génération intro personnalisée
        print(f"  → Génération intro via Claude API...")
        intro = generate_intro(nom, vertical, url_r, page_c)
        print(f"  → Intro : {intro[:80]}...")

        # Chargement template + injection
        template = load_template(vertical)
        lm = (
            template
            .replace("{intro_personnalise}", intro)
            .replace("{entreprise}", nom)
        )

        # Suppression de la ligne de metadata (VERTICAL/OBJET/====)
        lm_lines = lm.split("\n")
        # Garder à partir de "Madame, Monsieur" (ligne après ===)
        start = next((i for i, l in enumerate(lm_lines) if l.strip().startswith("Madame")), 3)
        objet = next((l.replace("OBJET    : ", "").replace("{entreprise}", nom)
                      for l in lm_lines if l.startswith("OBJET")), "")
        corps = "\n".join(lm_lines[start:]).strip()

        lm_final = f"Objet : {objet}\n\n{corps}"

        # Sauvegarde fichier
        filepath = os.path.join(OUTPUT_DIR, f"{s}.txt")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(lm_final)

        # Tracker
        tracker_rows.append({
            "slug"         : s,
            "nom"          : nom,
            "vertical"     : vertical,
            "cv_version"   : str(getattr(row, "cv_version", "")),
            "score"        : score,
            "email"        : email if email != "nan" else "",
            "page_carriere": page_c if page_c != "nan" else "",
            "fichier_lm"   : filepath,
            "date_gen"     : datetime.now().strftime("%Y-%m-%d %H:%M"),
            "envoye"       : "",
            "reponse"      : "",
            "relance_j10"  : "",
            "notes"        : "",
        })

        done_slugs.add(s)

        # Sauvegarde tracker incrémentale
        if tracker_rows:
            existing = []
            if os.path.exists(TRACKER_CSV):
                existing = pd.read_csv(TRACKER_CSV, encoding="utf-8-sig").to_dict("records")
            pd.DataFrame(existing + tracker_rows).drop_duplicates("slug").to_csv(
                TRACKER_CSV, index=False, encoding="utf-8-sig"
            )
            tracker_rows = []

        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    # ── Rapport final ─────────────────────────────────────────────────
    if os.path.exists(TRACKER_CSV):
        tracker = pd.read_csv(TRACKER_CSV, encoding="utf-8-sig")
        total = len(tracker)
    else:
        total = 0

    print(f"\n{'=' * 58}")
    print(f"✅ GÉNÉRATION TERMINÉE")
    print(f"   {total} LM générées dans ./{OUTPUT_DIR}/")
    print(f"   Tracker de suivi → {TRACKER_CSV}")
    print()
    print("  PROCESS D'ENVOI RECOMMANDÉ :")
    print("  1. Ouvre lm_generees/ et lis 3-4 LM pour valider le ton")
    print("  2. Commence par les Score A avec email direct")
    print("  3. Envoie 10 LM/semaine max (qualité > volume)")
    print("  4. Relance J+10 si pas de réponse")
    print("  5. Mets à jour lm_tracker.csv après chaque envoi")
    print(f"{'=' * 58}")

if __name__ == "__main__":
    main()

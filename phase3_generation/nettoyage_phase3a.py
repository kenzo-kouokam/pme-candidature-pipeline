#!/usr/bin/env python3
"""
PHASE 3A — Nettoyage CSV enrichi → entreprises_cibles.csv
Filtre les faux positifs, mappe les verticaux, sort par priorité.
Usage : python nettoyage_phase3a.py
"""

import pandas as pd
import re
from urllib.parse import urlparse

INPUT  = "entreprises_enrichi.csv"
OUTPUT = "entreprises_cibles.csv"
REJET  = "entreprises_rejetees.csv"   # pour audit

# ── Domaines faux positifs connus ─────────────────────────────────────────
DOMAINES_FP = {
    # Big 4 / grandes boîtes résolues à tort
    "ey.com", "kpmg.com", "deloitte.com", "pwc.com", "mckinsey.com",
    "bcg.com", "bain.com", "accenture.com", "capgemini.com",
    # Plateformes génériques
    "reddit.com", "linkedin.com", "facebook.com", "instagram.com",
    "twitter.com", "youtube.com", "google.com", "apple.com",
    # Médias / sites grand public
    "m6.fr", "tf1.fr", "bfmtv.com", "lefigaro.fr", "lemonde.fr",
    "journaldesfemmes.fr", "tv-programme.com", "voici.fr",
    "20minutes.fr", "leparisien.fr",
    # Institutionnels / hors scope
    "paris.fr", "gouvernement.fr", "pole-emploi.fr", "apec.fr",
    "businessfrance.fr", "ofii.fr", "sciences-u.fr",
    # Étrangers (URL résolue vers site hors France)
    "altinn.no", "info.altinn.no",
    # Dev / générique
    "github.com", "gitlab.com", "stackoverflow.com",
}

# ── Emails placeholder ─────────────────────────────────────────────────────
EMAIL_FP = re.compile(
    r"(nomprenom@|you@domain|@domain\.|@example\.|noreply|"
    r"test@|sentry|@schema|signalement|prismamedia|@2x|yvonbussy@stb)",
    re.IGNORECASE,
)

# ── Noms entreprises non-PME ───────────────────────────────────────────────
NOMS_FP = re.compile(
    r"\b(ernst.?young|ey\b|kpmg|deloitte|pwc|mckinsey|accenture|"
    r"capgemini|bouygues|orange|sfr|total|lvmh|bnp paribas|"
    r"société générale|axa|allianz|netflix|m6\b|tf1\b|amazon\b|"
    r"google\b|apple\b|microsoft\b)\b",
    re.IGNORECASE,
)

# ── Mapping secteur → vertical ─────────────────────────────────────────────
def get_vertical(secteur: str) -> str:
    s = str(secteur).strip()

    # ── Mapping codes NAF (Phase 1 API officielle) ────────────────────────
    NAF_MAP = {
        "62.01Z": "ESN / Informatique",    # Programmation informatique
        "62.02A": "ESN / Informatique",    # Conseil systèmes & logiciels
        "62.09Z": "ESN / Informatique",    # Autres activités informatiques
        "63.11Z": "ESN / Informatique",    # Traitement données, hébergement
        "63.12Z": "ESN / Informatique",    # Portails Internet
        "70.22Z": "Conseil / BI",          # Conseil affaires & gestion
        "70.21Z": "Conseil / BI",          # Relations publiques
        "66.19B": "Fintech / Assurance",   # Aux. services financiers
        "64.99Z": "Fintech / Assurance",   # Intermédiations monétaires
        "58.13Z": "Retail / E-com",        # Édition journaux (media)
        "59.12Z": "Retail / E-com",        # Post-production (media)
        "60.20Z": "Retail / E-com",        # Programmation & diffusion
    }
    if s in NAF_MAP:
        return NAF_MAP[s]

    # ── Fallback mots-clés (Phase 1 PagesJaunes / Kompass) ───────────────
    sl = s.lower()
    if any(k in sl for k in ["startup", "start-up", "scale-up", "scaleup"]):
        return "Startup / Scale-up"
    if any(k in sl for k in ["informatique", "esn", "services numériques", "éditeur logiciels",
                               "logiciels", "data science", "agence digitale", "numérique"]):
        return "ESN / Informatique"
    if any(k in sl for k in ["fintech", "assurance", "finance"]):
        return "Fintech / Assurance"
    if any(k in sl for k in ["e-commerce", "retail", "media", "média", "commerce"]):
        return "Retail / E-com"
    if any(k in sl for k in ["conseil", "management", "business intelligence", "analytique"]):
        return "Conseil / BI"
    return "Conseil / BI"

def get_cv_version(vertical: str) -> str:
    """Recommande quelle version CV utiliser selon le vertical."""
    if vertical in ("ESN / Informatique", "Fintech / Assurance", "Startup / Scale-up"):
        return "CV_DataScientist"   # ML en tête, Python/AWS/XGBoost first
    return "CV_DataAnalyst"          # BI en tête, Power BI/SQL/Excel first

# ── Vérification cohérence domaine / nom ──────────────────────────────────
def domaine_coherent(nom: str, url: str) -> bool:
    """Vérifie vaguement que le domaine de l'URL est lié au nom de l'entreprise."""
    if not url or not isinstance(url, str):
        return True   # pas d'URL = pas de raison de rejeter sur ce critère
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return True

    if domain in DOMAINES_FP:
        return False

    # Domaine étranger (.no, .de, .uk, .us, .it, .es) avec TLD non-francophone
    non_fr_tlds = [".no", ".de", ".uk", ".us", ".it", ".es", ".nl", ".se", ".dk"]
    if any(domain.endswith(t) for t in non_fr_tlds):
        return False

    return True

# ══════════════════════════════════════════════════════════════════════════
def main():
    df = pd.read_csv(INPUT, encoding="utf-8-sig")
    print(f"Chargé : {len(df)} lignes\n")

    rejects = []

    def reject(row, reason):
        r = row.to_dict()
        r["raison_rejet"] = reason
        rejects.append(r)

    keeps = []

    for _, row in df.iterrows():
        nom     = str(row.get("nom", "") or "")
        email   = str(row.get("email", "") or "")
        score   = str(row.get("score", "") or "")
        url_r   = str(row.get("url_resolue", "") or "")
        statut  = str(row.get("statut", "") or "")

        # Filtre 1 : garder seulement A et B
        if score not in ("A", "B"):
            reject(row, f"score_{score}")
            continue

        # Filtre 2 : statut ok obligatoire
        if statut != "ok":
            reject(row, f"statut_{statut}")
            continue

        # Filtre 3 : nom entreprise non-PME
        if NOMS_FP.search(nom):
            reject(row, "nom_grande_entreprise")
            continue

        # Filtre 4 : email placeholder
        if email and EMAIL_FP.search(email):
            reject(row, "email_placeholder")
            continue

        # Filtre 5 : URL résolue incohérente / faux positif
        if not domaine_coherent(nom, url_r):
            reject(row, "url_domaine_fp")
            continue

        keeps.append(row.to_dict())

    # ── Construire le DataFrame propre ─────────────────────────────────
    cibles = pd.DataFrame(keeps)
    if cibles.empty:
        print("⚠️  Aucune entreprise retenue après nettoyage.")
        return

    # Ajout colonne vertical + cv_version
    cibles["vertical"]   = cibles["secteur"].apply(get_vertical)
    cibles["cv_version"] = cibles["vertical"].apply(get_cv_version)

    # Tri : A d'abord, puis B ; dans chaque groupe tri par vertical puis nom
    cibles["_rank"] = cibles["score"].map({"A": 0, "B": 1})
    cibles = cibles.sort_values(["_rank", "vertical", "nom"]).drop(columns=["_rank"])
    cibles = cibles.reset_index(drop=True)

    # Colonnes finales utiles
    cols = ["nom", "vertical", "cv_version", "secteur", "score", "url_resolue",
            "email", "page_carriere", "has_form", "siren", "source"]
    cibles = cibles[[c for c in cols if c in cibles.columns]]

    # Export
    cibles.to_csv(OUTPUT, index=False, encoding="utf-8-sig")

    # Export rejets pour audit
    if rejects:
        pd.DataFrame(rejects).to_csv(REJET, index=False, encoding="utf-8-sig")

    # ── Rapport ────────────────────────────────────────────────────────
    print("=" * 55)
    print(f"✅ NETTOYAGE TERMINÉ")
    print("=" * 55)
    print(f"  Entrées initiales  : {len(df)}")
    print(f"  Retenues (cibles)  : {len(cibles)}")
    print(f"  Rejetées           : {len(rejects)}")
    print()
    print("  Répartition par vertical :")
    for v, g in cibles.groupby("vertical"):
        a = (g["score"] == "A").sum()
        b = (g["score"] == "B").sum()
        print(f"    {v:<25} {len(g):>3} cibles  (A={a} B={b})")
    print()
    print(f"  Emails disponibles  : {cibles['email'].notna().sum()}")
    print(f"  Pages carrière      : {cibles['page_carriere'].notna().sum()}")
    print()
    print(f"  → {OUTPUT} prêt")
    print(f"  → {REJET} pour audit des rejets")
    print()
    print("  Prochaine étape → python lm_generator.py")

if __name__ == "__main__":
    main()

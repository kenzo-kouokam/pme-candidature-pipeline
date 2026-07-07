#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  PHASE 1 — Scraper PME Île-de-France                           ║
║  Sortie : entreprises_brut.csv                                  ║
║                                                                  ║
║  Sources :                                                       ║
║    [1] API recherche-entreprises.api.gouv.fr  (officiel, free)  ║
║    [2] PagesJaunes                            (nom + URL site)  ║
║    [3] Kompass                                (nom + effectif)  ║
║                                                                  ║
║  Usage : python scraper_phase1.py                               ║
╚══════════════════════════════════════════════════════════════════╝
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import logging
import sys
import base64
import json as _json
from urllib.parse import quote_plus
from datetime import datetime

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scraper_phase1.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION — modifie ici si besoin
# ══════════════════════════════════════════════════════════════════════════════

OUTPUT_FILE = "entreprises_brut.csv"

# Délai aléatoire entre requêtes (secondes) — ne pas descendre sous 2s
DELAY_MIN = 2.5
DELAY_MAX = 5.5

# Pages max par secteur par source scraping (PJ/Kompass)
MAX_PAGES = 5  # ~10 résultats/page → ~50 entreprises/secteur/source

# ── Codes NAF prioritaires (API officielle) ───────────────────────────────
# Informatique / ESN / Data / Conseil
NAF_CODES = [
    "62.01Z",  # Programmation informatique
    "62.02A",  # Conseil en systèmes et logiciels
    "62.09Z",  # Autres activités informatiques
    "63.11Z",  # Traitement de données, hébergement
    "63.12Z",  # Portails Internet
    "70.22Z",  # Conseil pour les affaires et gestion
    "70.21Z",  # Relations publiques et communication
    "66.19B",  # Autres aux. services financiers (fintech)
    "64.99Z",  # Autres intermédiations monétaires
    "58.13Z",  # Édition de journaux (media)
    "59.12Z",  # Post-production (media)
    "60.20Z",  # Programmation et diffusion (media)
]

# ── Tranches effectif salariés (PME 20–300) ───────────────────────────────
# Code INSEE : 12=20-49, 21=50-99, 22=100-199, 31=200-249, 32=250-499
TRANCHES_EFFECTIF = ["12", "21", "22", "31"]

# ── Secteurs pour PagesJaunes ─────────────────────────────────────────────
SECTEURS_PJ = [
    "entreprise services numériques ESN",
    "conseil informatique",
    "éditeur logiciels",
    "cabinet conseil management",
    "fintech",
    "data science analytique",
    "business intelligence",
    "e-commerce",
    "assurance",
    "agence digitale numérique",
    "media numérique",
]

# ── Mots-clés pour Kompass ────────────────────────────────────────────────
SECTEURS_KOMPASS = [
    "services informatiques",
    "conseil management",
    "éditeur logiciels",
    "fintech finance technologie",
    "data analytics",
    "e-commerce retail digital",
]

# ── User-Agents alternés (anti-détection basique) ─────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_session() -> requests.Session:
    """Crée une session avec un User-Agent aléatoire."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",
    })
    return s


def sleep_random(label: str = ""):
    t = random.uniform(DELAY_MIN, DELAY_MAX)
    log.info(f"  ⏳ Pause {t:.1f}s {label}")
    time.sleep(t)


def _text(card, selectors: list) -> str | None:
    """Tente plusieurs sélecteurs CSS, retourne le premier texte trouvé."""
    for sel in selectors:
        try:
            el = card.select_one(sel)
            if el:
                txt = el.get_text(strip=True)
                if txt:
                    return txt
        except Exception:
            continue
    return None


def _href(card, selectors: list) -> str | None:
    """Tente plusieurs sélecteurs CSS, retourne le premier href http trouvé."""
    for sel in selectors:
        try:
            el = card.select_one(sel)
            if el:
                href = el.get("href", "")
                if href.startswith("http"):
                    return href
        except Exception:
            continue
    return None


def _safe_get(session, url: str, timeout: int = 15) -> requests.Response | None:
    """GET avec gestion 429 / erreurs réseau."""
    try:
        r = session.get(url, timeout=timeout)
        if r.status_code == 429:
            log.warning("  ⛔ Rate limited (429) — pause 45s")
            time.sleep(45)
            r = session.get(url, timeout=timeout)
        if r.status_code != 200:
            log.warning(f"  HTTP {r.status_code} — skip")
            return None
        return r
    except requests.RequestException as e:
        log.error(f"  Erreur réseau : {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# SOURCE 1 — API officielle gouvernementale (équivalent Societe.com/Infogreffe)
# ══════════════════════════════════════════════════════════════════════════════

def scrape_api_officielle() -> list[dict]:
    """
    API recherche-entreprises.api.gouv.fr
    Données SIRENE officielles — filtrées par département IDF + code NAF.
    Aucune clé API requise.

    Fix v2 : suppression des paramètres non supportés (tranche_effectif_salarie,
    est_active, region). Filtrage par département IDF + filtre taille en post-traitement.
    """
    log.info("\n" + "═" * 60)
    log.info("[SOURCE 1] API officielle recherche-entreprises.api.gouv.fr")
    log.info("═" * 60)

    # Départements Île-de-France
    IDF_DEPTS = ["75", "77", "78", "91", "92", "93", "94", "95"]

    # Tranches effectif PME cibles (filtre post-API) :
    # "12"=20-49, "21"=50-99, "22"=100-199, "31"=200-249, "32"=250-499
    TRANCHES_CIBLES = {"12", "21", "22", "31", "32"}

    results = []
    base_url = "https://recherche-entreprises.api.gouv.fr/search"

    for naf in NAF_CODES:
        for dept in IDF_DEPTS:
            page = 1
            while page <= 3:  # max 3 pages × 25 = 75 résultats/combo
                params = {
                    "activite_principale": naf,
                    "departement": dept,
                    "page": page,
                    "per_page": 25,
                }
                url = base_url + "?" + "&".join(f"{k}={v}" for k, v in params.items())
                log.info(f"  NAF {naf} | dept {dept} | page {page}")

                try:
                    r = requests.get(url, timeout=15)
                    if r.status_code != 200:
                        log.warning(f"  HTTP {r.status_code} — skip")
                        break

                    data = r.json()
                    entreprises = data.get("results", [])

                    if not entreprises:
                        break

                    added = 0
                    for e in entreprises:
                        nom = e.get("nom_complet") or e.get("nom_raison_sociale", "")
                        siege = e.get("siege", {})
                        adresse = siege.get("libelle_commune", "")
                        siren = e.get("siren", "")
                        tranche = str(e.get("tranche_effectif_salarie", "") or "")

                        # Filtre taille PME en post-traitement
                        if tranche and tranche not in TRANCHES_CIBLES:
                            continue

                        url_societe = (
                            f"https://www.societe.com/societe/"
                            f"{nom.lower().replace(' ', '-').replace('/', '')}-{siren}.html"
                            if siren else None
                        )

                        results.append({
                            "nom": nom.strip(),
                            "secteur": naf,
                            "url_site": None,
                            "adresse": adresse,
                            "taille": tranche,
                            "siren": siren,
                            "url_societe": url_societe,
                            "source": "API_officielle",
                        })
                        added += 1

                    log.info(f"    → {added} PME retenues / {len(entreprises)} reçues | total {len(results)}")

                    total_pages = data.get("total_pages", 1)
                    if page >= total_pages or page >= 3:
                        break

                    page += 1
                    time.sleep(random.uniform(0.5, 1.2))

                except Exception as e:
                    log.error(f"  Erreur API : {e}")
                    break

    log.info(f"\n✅ API officielle : {len(results)} PME récoltées")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# SOURCE 2 — PagesJaunes
# ══════════════════════════════════════════════════════════════════════════════

def _decode_pjlb(el) -> str | None:
    """
    Décode l'URL encodée en base64 dans l'attribut data-pjlb de PagesJaunes.
    Structure : data-pjlb='{"url":"<base64>","ucod":"b64u8"}'
    """
    raw = el.get("data-pjlb", "") if el else ""
    if not raw:
        return None
    try:
        data = _json.loads(raw)
        b64 = data.get("url", "")
        if not b64:
            return None
        # Padding base64 (multiple de 4)
        decoded = base64.b64decode(b64 + "==").decode("utf-8", errors="ignore")
        return decoded or None
    except Exception:
        return None


def scrape_pagesjaunes(session: requests.Session) -> list[dict]:
    """
    Scrape PagesJaunes par secteur, Île-de-France.

    Sélecteurs confirmés sur le HTML réel (juin 2025) :
    - Cartes     : li.bi (li avec class 'bi')
    - Nom        : a.bi-denomination h3
    - URL site   : a.btn_external_link → data-pjlb → base64 decode
    - URL profil : a.bi-denomination → data-pjlb → base64 decode (fallback Phase 2)
    """
    log.info("\n" + "═" * 60)
    log.info("[SOURCE 2] PagesJaunes — sélecteurs v2 (base64 decode)")
    log.info("═" * 60)

    results = []
    base_url = "https://www.pagesjaunes.fr/annuaire/chercherlespros"

    for secteur in SECTEURS_PJ:
        log.info(f"\n  Secteur : {secteur}")

        for page in range(1, MAX_PAGES + 1):
            url = (
                f"{base_url}"
                f"?quoiqui={quote_plus(secteur)}"
                f"&ou={quote_plus('Ile-de-France')}"
                f"&page={page}"
            )
            log.info(f"    Page {page} → {url}")

            r = _safe_get(session, url)
            if r is None:
                break

            soup = BeautifulSoup(r.text, "lxml")

            # ── Détection blocage ──────────────────────────────────────────
            if "captcha" in r.text.lower() or "accès refusé" in r.text.lower():
                log.warning("  ⚠️  Blocage détecté — pause 20s puis secteur suivant")
                time.sleep(20)
                break

            # ── Cartes résultats : li avec id='bi-XXXXXX' (vraies fiches) ─
            # Les li.bi sans id numérique sont des pubs/placeholders JS
            import re as _re
            cards = soup.find_all("li", id=_re.compile(r"^bi-\d+"))
            if not cards:
                log.warning(f"    Aucune fiche réelle (id=bi-XXXX) page {page} — fin secteur")
                break

            found_urls = 0
            for card in cards:
                # ── Nom ───────────────────────────────────────────────────
                name_el = card.select_one("a.bi-denomination h3")
                if not name_el:
                    name_el = card.select_one("h3")
                name = name_el.get_text(strip=True) if name_el else None
                if not name:
                    continue

                # ── URL site web (encodée base64 dans btn_external_link) ──
                # Confirmé sur HTML réel : data-pjlb contient l'URL en base64
                website = None
                ext_btns = card.find_all("a", class_="btn_external_link")
                for btn in ext_btns:
                    decoded = _decode_pjlb(btn)
                    if decoded and decoded.startswith("http") and "pagesjaunes.fr" not in decoded:
                        website = decoded
                        found_urls += 1
                        break

                # ── URL profil PagesJaunes (fallback pour Phase 2) ────────
                pj_url = None
                denom_el = card.select_one("a.bi-denomination")
                if denom_el:
                    # Cas 1 : href direct (non-JS)
                    href = denom_el.get("href", "")
                    if href.startswith("https://www.pagesjaunes.fr/pros/") and not href.endswith("#"):
                        pj_url = href
                    # Cas 2 : encodé dans data-pjlb
                    elif denom_el.get("data-pjlb"):
                        decoded_path = _decode_pjlb(denom_el)
                        if decoded_path and decoded_path.startswith("/pros"):
                            pj_url = "https://www.pagesjaunes.fr" + decoded_path.split("#")[0]

                results.append({
                    "nom": name.strip(),
                    "secteur": secteur,
                    "url_site": website,
                    "adresse": "Île-de-France",
                    "taille": None,
                    "siren": None,
                    "url_societe": pj_url,   # URL PJ stockée dans url_societe pour Phase 2
                    "source": "PagesJaunes",
                })

            log.info(f"    → {len(cards)} fiches | {found_urls} URLs site extraites | total {len(results)}")
            sleep_random("(PJ)")

        # Rotation session entre secteurs
        session = get_session()

    log.info(f"\n✅ PagesJaunes : {len(results)} entrées brutes")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# SOURCE 3 — Kompass
# ══════════════════════════════════════════════════════════════════════════════

def scrape_kompass(session: requests.Session) -> list[dict]:
    """
    Scrape Kompass.fr par secteur, Île-de-France.
    Récupère : nom, URL, effectif.
    """
    log.info("\n" + "═" * 60)
    log.info("[SOURCE 3] Kompass")
    log.info("═" * 60)

    results = []
    base_url = "https://fr.kompass.com/searchCompany"

    for secteur in SECTEURS_KOMPASS:
        log.info(f"\n  Secteur : {secteur}")

        for page in range(1, MAX_PAGES + 1):
            start = (page - 1) * 25
            url = (
                f"{base_url}"
                f"?text={quote_plus(secteur)}"
                f"&country=fr"
                f"&county=FR-IDF"
                f"&start={start}"
            )
            log.info(f"    Page {page} → {url}")

            r = _safe_get(session, url)
            if r is None:
                break

            soup = BeautifulSoup(r.text, "lxml")

            if "captcha" in r.text.lower():
                log.warning("  ⚠️  Blocage Kompass — pause 20s")
                time.sleep(20)
                break

            # ── Sélecteurs résultats Kompass ──────────────────────────────
            cards = (
                soup.select("div.companyCard")
                or soup.select("div[class*='company-card']")
                or soup.select("article[class*='company']")
                or soup.select("li[class*='company']")
                or []
            )

            if not cards:
                log.warning(f"    Aucune carte Kompass page {page}")
                break

            for card in cards:
                name = _text(card, [
                    "h2.companyName a",
                    "h2 a", "h3 a",
                    "[class*='company-name']",
                    "[class*='companyName']",
                ])

                website = _href(card, [
                    "a[class*='website']",
                    "a[title*='site']",
                    "a[href^='http']:not([href*='kompass'])",
                ])

                taille = _text(card, [
                    "[class*='employees']",
                    "[class*='effectif']",
                    "[class*='staff']",
                    "[class*='size']",
                ])

                if name:
                    results.append({
                        "nom": name.strip(),
                        "secteur": secteur,
                        "url_site": website,
                        "adresse": "Île-de-France",
                        "taille": taille,
                        "siren": None,
                        "url_societe": None,
                        "source": "Kompass",
                    })

            log.info(f"    → {len(cards)} cartes | total {len(results)}")
            sleep_random("(Kompass)")

        session = get_session()

    log.info(f"\n✅ Kompass : {len(results)} entrées brutes")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# DÉDUPLICATION + EXPORT
# ══════════════════════════════════════════════════════════════════════════════

def deduplicate_and_export(all_results: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(all_results)

    log.info(f"\n{'═' * 60}")
    log.info(f"DÉDUPLICATION & EXPORT")
    log.info(f"{'═' * 60}")
    log.info(f"  Total brut : {len(df)} lignes")

    # Nettoyage noms
    df["nom"] = df["nom"].str.strip().str.title()
    df = df[df["nom"].notna() & (df["nom"] != "")]

    # Déduplication sur nom (garde la ligne avec le plus d'infos)
    df["_score"] = (
        df["url_site"].notna().astype(int)
        + df["siren"].notna().astype(int)
        + df["taille"].notna().astype(int)
    )
    df = df.sort_values("_score", ascending=False)
    df = df.drop_duplicates(subset=["nom"], keep="first")
    df = df.drop(columns=["_score"])

    log.info(f"  Après dédup : {len(df)} entreprises uniques")

    # Réordonne colonnes
    cols = ["nom", "secteur", "url_site", "adresse", "taille", "siren", "url_societe", "source"]
    df = df[cols]

    # Stats par source
    log.info("\n  Répartition par source :")
    for src, count in df["source"].value_counts().items():
        log.info(f"    {src:<25} {count:>5} entreprises")

    log.info(f"\n  Entreprises avec URL site : {df['url_site'].notna().sum()}")
    log.info(f"  Entreprises avec SIREN   : {df['siren'].notna().sum()}")

    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    log.info(f"\n✅ CSV sauvegardé → {OUTPUT_FILE}")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    start_time = datetime.now()
    log.info("╔" + "═" * 58 + "╗")
    log.info("║  PHASE 1 — Scraper PME Île-de-France" + " " * 20 + "║")
    log.info(f"║  Démarrage : {start_time.strftime('%Y-%m-%d %H:%M:%S')}" + " " * 25 + "║")
    log.info("╚" + "═" * 58 + "╝")

    all_results = []

    # ── Source 1 : API officielle (données SIRENE, aucun blocage) ──────────
    api_results = scrape_api_officielle()
    all_results.extend(api_results)

    # ── Source 2 : PagesJaunes ─────────────────────────────────────────────
    session_pj = get_session()
    pj_results = scrape_pagesjaunes(session_pj)
    all_results.extend(pj_results)

    # ── Source 3 : Kompass ─────────────────────────────────────────────────
    session_kp = get_session()
    kp_results = scrape_kompass(session_kp)
    all_results.extend(kp_results)

    # ── Fusion + export ────────────────────────────────────────────────────
    df = deduplicate_and_export(all_results)

    elapsed = (datetime.now() - start_time).seconds // 60
    log.info(f"\n🏁 Phase 1 terminée en ~{elapsed} min")
    log.info(f"   {len(df)} PME dans {OUTPUT_FILE}")
    log.info(f"\n   Prochaine étape → python enrichissement_phase2.py")


if __name__ == "__main__":
    main()
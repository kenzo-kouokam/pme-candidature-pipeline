#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  PHASE 2 — Enrichissement PME                                   ║
║                                                                  ║
║  Input  : entreprises_brut.csv                                  ║
║  Output : entreprises_enrichi.csv                               ║
║                                                                  ║
║  Pour chaque entreprise :                                        ║
║    1. Résout l'URL site (directe ou via profil PagesJaunes)     ║
║    2. Scrape le site → email + page carrière                    ║
║    3. Score A/B/C/D                                             ║
║                                                                  ║
║  Usage : python enrichissement_phase2.py                        ║
╚══════════════════════════════════════════════════════════════════╝

Score :
  A — email trouvé + page carrière active
  B — page carrière trouvée, pas d'email direct
  C — seulement formulaire de contact ou email générique
  D — rien trouvé (site inaccessible ou aucun contact)
"""

import os
import subprocess
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import random
import logging
import sys
import json as _json
import base64
from urllib.parse import urljoin, urlparse, quote_plus
from datetime import datetime

# ── Auto-install duckduckgo_search si absent ──────────────────────────────────
try:
    from duckduckgo_search import DDGS
except ImportError:
    print("Installation de duckduckgo-search...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "duckduckgo-search", "-q"])
    from duckduckgo_search import DDGS

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("enrichissement_phase2.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

INPUT_FILE  = "entreprises_brut.csv"
OUTPUT_FILE = "entreprises_enrichi.csv"

DELAY_MIN = 1.0
DELAY_MAX = 2.5
TIMEOUT   = 10  # secondes par requête

# ── Patterns page carrière ─────────────────────────────────────────────
# Limités aux plus courants pour accélérer
CAREER_URL_PATTERNS = [
    "/recrutement", "/carrieres", "/careers", "/jobs",
    "/rejoindre", "/nous-rejoindre", "/emploi", "/postuler",
]

# ── Mots-clés page carrière (dans le texte des liens) ────────────────────
CAREER_KEYWORDS = [
    "carrière", "carrieres", "recrutement", "recruter",
    "rejoindre", "offres d'emploi", "offres emploi", "travailler",
    "candidature", "career", "jobs", "hiring", "postuler",
    "nous rejoindre", "intégrer", "equipe",
]

# ── Patterns email à exclure (génériques) ────────────────────────────────
EMAIL_EXCLUDE = re.compile(
    r"(noreply|no-reply|donotreply|support|info@example|"
    r"test@|\.png|\.jpg|\.gif|\.svg|sentry|@schema|@2x)",
    re.IGNORECASE,
)

# ── Regex email ──────────────────────────────────────────────────────────
EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

# Blacklist DDG — liste exacte demandée + compléments génériques
DDG_BLACKLIST = {
    "linkedin.com", "pagesjaunes.fr", "societe.com", "manageo.fr",
    "pappers.fr", "verif.com", "kompass.com", "jurigtravail.com",
    "infogreffe.fr", "twitter.com", "facebook.com", "instagram.com",
    # Compléments
    "pages-jaunes.fr", "google.com", "google.fr", "bing.com",
    "youtube.com", "wikipedia.org", "lefigaro.fr", "bfmtv.com",
    "lemonde.fr", "lequipe.fr", "leboncoin.fr", "indeed.com",
    "welcometothejungle.com", "jobteaser.com", "monster.fr",
    "hellowork.com", "glassdoor.fr", "cadremploi.fr", "apec.fr",
    "yelp.fr", "tripadvisor.fr", "mappy.com", "20minutes.fr",
}

# Alias pour compatibilité avec le reste du code
BLACKLIST_DOMAINS = DDG_BLACKLIST


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
    })
    return s


def safe_get(session, url: str, timeout: int = TIMEOUT) -> requests.Response | None:
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code in (200, 201):
            return r
        if r.status_code == 429:
            log.warning("  Rate-limited (429) — pause 40s")
            time.sleep(40)
            r = session.get(url, timeout=timeout, allow_redirects=True)
            return r if r.status_code == 200 else None
        return None
    except requests.exceptions.SSLError:
        try:
            r = session.get(url, timeout=timeout, verify=False, allow_redirects=True)
            return r if r.status_code == 200 else None
        except Exception:
            return None
    except Exception:
        return None


def find_url_via_ddg(nom: str, siren: str = "") -> str | None:
    """
    Cherche le site officiel d'une entreprise via DuckDuckGo.

    Requête : "{nom entreprise}" site officiel France
    Si SIREN disponible, ajoute-le pour affiner (évite les homonymes).
    Filtre les domaines de DDG_BLACKLIST et tout domaine contenant "annuaire".
    Retourne l'URL racine (scheme + netloc) ou None.
    """
    nom_clean = re.sub(r"[^\w\s\-&]", " ", str(nom)).strip()[:70]
    siren_clean = str(siren).strip() if siren and str(siren) not in ("nan", "", "None") else ""

    queries = [
        f'"{nom_clean}" site officiel France',
        f'{nom_clean}{" " + siren_clean if siren_clean else ""} entreprise France',
    ]

    try:
        with DDGS() as ddg:
            for query in queries:
                results = list(ddg.text(query, region="fr-fr", max_results=8))
                for r in results:
                    href = r.get("href", "")
                    if not href.startswith("http"):
                        continue
                    parsed = urlparse(href)
                    domain = parsed.netloc.lower().replace("www.", "")

                    # Filtre liste noire exacte
                    if any(bl in domain for bl in DDG_BLACKLIST):
                        continue
                    # Filtre domaines contenant "annuaire"
                    if "annuaire" in domain:
                        continue
                    # Doit avoir un TLD valide
                    if not re.search(r"\.[a-z]{2,}$", domain):
                        continue

                    root = f"{parsed.scheme}://{parsed.netloc}"
                    log.info(f"    DDG → {root}")
                    return root

                time.sleep(random.uniform(1.5, 2.5))

    except Exception as e:
        log.debug(f"    DDG erreur : {e}")

    return None


def sleep_random():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def normalize_url(url: str) -> str | None:
    """Ajoute https:// si manquant, nettoie l'URL."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    # Garder seulement scheme + netloc + path (sans params ni fragments)
    return f"{parsed.scheme}://{parsed.netloc}"


def base_url(url: str) -> str:
    """Retourne l'origine (scheme + netloc) d'une URL."""
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


# ══════════════════════════════════════════════════════════════════════════════
# RÉSOLUTION URL — PagesJaunes profil → URL site réel
# ══════════════════════════════════════════════════════════════════════════════

def resolve_pj_profile(session, pj_url: str) -> str | None:
    """
    Visite la fiche PagesJaunes d'une entreprise et extrait l'URL de son site web.
    Le lien site est encodé en base64 dans data-pjlb sur a.btn_external_link.
    """
    r = safe_get(session, pj_url)
    if not r:
        return None

    soup = BeautifulSoup(r.text, "lxml")

    # Méthode 1 : btn_external_link avec data-pjlb (base64)
    for btn in soup.find_all("a", class_="btn_external_link"):
        raw = btn.get("data-pjlb", "")
        if not raw:
            continue
        try:
            data = _json.loads(raw)
            b64 = data.get("url", "")
            decoded = base64.b64decode(b64 + "==").decode("utf-8", errors="ignore")
            if decoded.startswith("http") and "pagesjaunes.fr" not in decoded:
                return decoded
        except Exception:
            continue

    # Méthode 2 : lien externe direct (href http hors pagesjaunes)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http") and "pagesjaunes.fr" not in href:
            if any(cls in a.get("class", []) for cls in ["url-website", "lien-site", "website"]):
                return href

    return None


# ══════════════════════════════════════════════════════════════════════════════
# EXTRACTION EMAIL
# ══════════════════════════════════════════════════════════════════════════════

def extract_emails(soup: BeautifulSoup, html_text: str) -> list[str]:
    """Cherche emails dans le HTML. Priorité aux mailto: puis au texte brut."""
    found = set()

    # 1. Balises mailto:
    for a in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
        mail = a["href"].replace("mailto:", "").split("?")[0].strip()
        if EMAIL_REGEX.match(mail) and not EMAIL_EXCLUDE.search(mail):
            found.add(mail.lower())

    # 2. Texte brut (protection obfuscation basique)
    for match in EMAIL_REGEX.finditer(html_text):
        mail = match.group().lower()
        if not EMAIL_EXCLUDE.search(mail):
            found.add(mail)

    # Trier : préférer contact/rh/recrutement plutôt que info/admin
    priority = ["recrutement", "rh", "contact", "hello", "bonjour"]

    def _rank(email):
        for i, kw in enumerate(priority):
            if kw in email:
                return i
        return len(priority)

    return sorted(found, key=_rank)


# ══════════════════════════════════════════════════════════════════════════════
# DÉTECTION PAGE CARRIÈRE
# ══════════════════════════════════════════════════════════════════════════════

def find_career_page(session, site_base: str, soup: BeautifulSoup) -> str | None:
    """
    1. Cherche un lien carrière dans le HTML de la page d'accueil
    2. Teste les patterns d'URL classiques
    """
    # ── Étape 1 : liens dans la nav/page ─────────────────────────────────
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        href = a["href"].lower()
        if any(kw in text or kw in href for kw in CAREER_KEYWORDS):
            full = urljoin(site_base, a["href"])
            if urlparse(full).netloc == urlparse(site_base).netloc:
                return full

    # ── Étape 2 : test patterns URL ──────────────────────────────────────
    for pattern in CAREER_URL_PATTERNS:
        url = site_base.rstrip("/") + pattern
        r = safe_get(session, url, timeout=8)
        if r and r.status_code == 200:
            # Vérifier que la page a du contenu réel (pas une 404 soft)
            content = r.text.lower()
            if any(kw in content for kw in CAREER_KEYWORDS):
                return url
        time.sleep(random.uniform(0.3, 0.8))  # délai court entre tests URL

    return None


def has_contact_form(soup: BeautifulSoup) -> bool:
    """Détecte la présence d'un formulaire de contact."""
    forms = soup.find_all("form")
    for form in forms:
        text = form.get_text(strip=True).lower()
        inputs = form.find_all("input", type=lambda t: t and t.lower() in ["text", "email", "tel"])
        if inputs and any(kw in text for kw in ["contact", "message", "envoyer", "submit"]):
            return True
    # Aussi : lien /contact
    for a in soup.find_all("a", href=True):
        if "contact" in a["href"].lower():
            return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# SCORING
# ══════════════════════════════════════════════════════════════════════════════

def score(email: str | None, career_url: str | None, has_form: bool) -> str:
    """
    A — email spécifique (rh/recrutement/contact) + page carrière
    B — page carrière trouvée, sans email direct
    C — email générique (info@...) OU seulement formulaire contact
    D — rien
    """
    has_email = bool(email)
    has_career = bool(career_url)
    is_priority_email = has_email and any(
        kw in (email or "") for kw in ["recrutement", "rh", "career", "contact", "hello"]
    )

    if has_email and has_career:
        return "A"
    if has_career:
        return "B"
    if has_email or has_form:
        return "C"
    return "D"


# ══════════════════════════════════════════════════════════════════════════════
# TRAITEMENT D'UNE ENTREPRISE
# ══════════════════════════════════════════════════════════════════════════════

def enrich_one(session, row: dict) -> dict:
    """
    Enrichit une ligne du CSV brut.
    Retourne le dict complété avec : url_resolue, email, page_carriere, has_form, score.
    """
    result = {
        "url_resolue": None,
        "email": None,
        "page_carriere": None,
        "has_form": False,
        "score": "D",
        "statut": "non_traité",
    }

    # ── 1. Résolution URL ─────────────────────────────────────────────────
    url_site    = row.get("url_site")
    url_societe = row.get("url_societe", "")

    site_url = None

    def _is_real_site(u: str) -> bool:
        """Retourne True si l'URL pointe vers un vrai site d'entreprise (pas un annuaire)."""
        if not u or not isinstance(u, str) or not u.startswith("http"):
            return False
        domain = urlparse(u).netloc.lower().replace("www.", "")
        return not any(bl in domain for bl in DDG_BLACKLIST) and "annuaire" not in domain

    if _is_real_site(url_site):
        site_url = url_site
    elif isinstance(url_societe, str) and "pagesjaunes.fr/pros" in url_societe:
        log.info(f"    → Résolution PJ : {url_societe[:60]}")
        site_url = resolve_pj_profile(session, url_societe)
        sleep_random()
    elif _is_real_site(url_societe):
        site_url = url_societe

    if not site_url:
        nom    = row.get("nom", "")
        siren  = row.get("siren", "")
        log.info(f"    → DDG : {nom[:50]}")
        site_url = find_url_via_ddg(nom, siren)
        sleep_random()
        if not site_url:
            result["statut"] = "url_introuvable"
            return result

    site_base = base_url(site_url)
    result["url_resolue"] = site_base

    # ── 2. Scraping page d'accueil ────────────────────────────────────────
    log.info(f"    → Scraping : {site_base}")
    r = safe_get(session, site_base)
    if not r:
        result["statut"] = "site_inaccessible"
        return result

    soup = BeautifulSoup(r.text, "lxml")

    # ── 3. Extraction emails ──────────────────────────────────────────────
    emails = extract_emails(soup, r.text)
    result["email"] = emails[0] if emails else None

    # ── 4. Détection formulaire de contact ────────────────────────────────
    result["has_form"] = has_contact_form(soup)

    # ── 5. Recherche page carrière ────────────────────────────────────────
    career = find_career_page(session, site_base, soup)
    result["page_carriere"] = career

    # ── 6. Score ──────────────────────────────────────────────────────────
    result["score"] = score(result["email"], career, result["has_form"])
    result["statut"] = "ok"

    return result


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    start = datetime.now()
    log.info("╔" + "═" * 58 + "╗")
    log.info("║  PHASE 2 — Enrichissement PME" + " " * 28 + "║")
    log.info(f"║  Démarrage : {start.strftime('%Y-%m-%d %H:%M:%S')}" + " " * 25 + "║")
    log.info("╚" + "═" * 58 + "╝")

    # ── Lecture CSV (reprend depuis enrichi si existant) ──────────────────
    try:
        df_brut = pd.read_csv(INPUT_FILE, encoding="utf-8-sig")
    except FileNotFoundError:
        log.error(f"❌ Fichier introuvable : {INPUT_FILE}")
        sys.exit(1)

    if os.path.exists(OUTPUT_FILE):
        try:
            df = pd.read_csv(OUTPUT_FILE, encoding="utf-8-sig")
            log.info(f"\n📂 Reprise depuis {OUTPUT_FILE} ({len(df)} lignes)")
        except Exception:
            df = df_brut.copy()
            log.info(f"\n📂 {len(df)} entreprises chargées depuis {INPUT_FILE}")
    else:
        df = df_brut.copy()
        log.info(f"\n📂 {len(df)} entreprises chargées depuis {INPUT_FILE}")

    # Colonnes à ajouter
    for col in ["url_resolue", "email", "page_carriere", "has_form", "score", "statut"]:
        if col not in df.columns:
            df[col] = None

    # Reprendre là où on s'est arrêté (skip url_introuvable aussi = sera retenté)
    mask_todo = df["statut"].isna() | (df["statut"] == "non_traité") | (df["statut"] == "url_introuvable")
    todo = df[mask_todo].index.tolist()
    log.info(f"   À traiter : {len(todo)} | Déjà fait : {len(df) - len(todo)}")

    session = get_session()
    stats = {"A": 0, "B": 0, "C": 0, "D": 0, "err": 0}

    for i, idx in enumerate(todo, 1):
        row = df.loc[idx].to_dict()
        nom = row.get("nom", "?")

        log.info(f"\n[{i}/{len(todo)}] {nom[:50]}")

        try:
            enriched = enrich_one(session, row)
            for col, val in enriched.items():
                df.at[idx, col] = val

            sc = enriched["score"]
            stats[sc] = stats.get(sc, 0) + 1
            log.info(
                f"    Score {sc} | email: {enriched['email'] or '—'} | "
                f"carrière: {'✓' if enriched['page_carriere'] else '—'}"
            )

        except Exception as e:
            log.error(f"    Erreur inattendue : {e}")
            df.at[idx, "statut"] = f"erreur: {str(e)[:80]}"
            stats["err"] = stats.get("err", 0) + 1

        # Sauvegarde incrémentale toutes les 10 entreprises
        if i % 10 == 0:
            df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
            log.info(f"    💾 Sauvegarde ({i}/{len(todo)})")

        # Rapport de progression toutes les 50 entreprises
        if i % 50 == 0:
            ddg_found  = df["url_resolue"].notna().sum()
            emails_    = df["email"].notna().sum()
            careers_   = df["page_carriere"].notna().sum()
            elapsed_s  = int((datetime.now() - start).total_seconds())
            eta_s      = int(elapsed_s / i * (len(todo) - i)) if i else 0
            log.info(
                f"\n{'─'*55}\n"
                f"  RAPPORT [{i}/{len(todo)}]  —  "
                f"{elapsed_s//60}min écoulées, ~{eta_s//60}min restantes\n"
                f"  URLs DDG    : {ddg_found}\n"
                f"  Emails      : {emails_}\n"
                f"  Carrières   : {careers_}\n"
                f"  Scores      : A={stats['A']} B={stats['B']} "
                f"C={stats['C']} D={stats['D']} err={stats['err']}\n"
                f"{'─'*55}"
            )

        # Rotation session toutes les 30 entreprises (anti-blocage)
        if i % 30 == 0:
            session = get_session()

        sleep_random()

    # ── Export final ──────────────────────────────────────────────────────
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    elapsed = (datetime.now() - start).seconds // 60
    urls_ddg = df["url_resolue"].notna().sum()
    emails_n = df["email"].notna().sum()
    careers_n = df["page_carriere"].notna().sum()
    log.info(f"\n{'═' * 60}")
    log.info(f"✅ PHASE 2 TERMINÉE en ~{elapsed} min")
    log.info(f"   {OUTPUT_FILE} — {len(df)} entreprises")
    log.info(f"\n   URLs trouvées via DDG  : {urls_ddg}")
    log.info(f"   Emails trouvés         : {emails_n}")
    log.info(f"   Pages carrière         : {careers_n}")
    log.info(f"\n   Répartition scores :")
    log.info(f"     A (email + carrière)  : {stats.get('A', 0):>4}")
    log.info(f"     B (carrière seule)    : {stats.get('B', 0):>4}")
    log.info(f"     C (email/form seul)   : {stats.get('C', 0):>4}")
    log.info(f"     D (rien trouvé)       : {stats.get('D', 0):>4}")
    log.info(f"     Erreurs               : {stats.get('err', 0):>4}")
    log.info(f"\n   Prochaine étape → Phase 3 : templates LM")
    log.info(f"{'═' * 60}")


if __name__ == "__main__":
    main()

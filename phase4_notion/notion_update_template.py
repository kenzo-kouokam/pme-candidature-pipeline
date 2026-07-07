#!/usr/bin/env python3
"""
notion_update_template.py — Template de mise à jour quotidienne Notion
Copier-coller ce fichier pour chaque session de mise à jour.

Usage :
  cp notion_update_template.py notion_updates_JJMOIS.py
  # Remplir les sections UPDATES et CREATES
  python notion_updates_JJMOIS.py
"""

import os
import time
import unicodedata
import requests

TOKEN  = os.environ.get("NOTION_TOKEN", "")
API    = "https://api.notion.com/v1"
PME_DB = os.environ.get("NOTION_PME_DB_ID", "")   # base candidatures spontanées
GG_DB  = os.environ.get("NOTION_GG_DB_ID", "")    # base grands groupes / offres ciblées

HDRS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


# ── API helpers ───────────────────────────────────────────────────────────────

def post(path, body):
    r = requests.post(f"{API}/{path}", headers=HDRS, json=body, timeout=20)
    if not r.ok:
        raise RuntimeError(f"POST {path} → {r.status_code}: {r.text[:300]}")
    return r.json()

def patch(path, body):
    r = requests.patch(f"{API}/{path}", headers=HDRS, json=body, timeout=20)
    if not r.ok:
        raise RuntimeError(f"PATCH {path} → {r.status_code}: {r.text[:300]}")
    return r.json()


# ── Constructeurs de propriétés Notion ────────────────────────────────────────

def p_title(v):  return {"title":     [{"text": {"content": v[:2000]}}]}
def p_text(v):   return {"rich_text": [{"text": {"content": v[:2000]}}]}
def p_select(v): return {"select": {"name": v}} if v else {"select": None}
def p_email(v):  return {"email": v} if v else {"email": None}
def p_date(v):   return {"date": {"start": v}} if v else {"date": None}


# ── Normalisation (accents → ASCII, lowercase) ────────────────────────────────

def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.lower().strip()


# ── Chargement d'une base avec pagination ─────────────────────────────────────

def load_pages(db_id: str) -> list[dict]:
    pages, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = post(f"databases/{db_id}/query", body)
        pages.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        time.sleep(0.25)
    return pages


# ── Accesseurs de propriétés ──────────────────────────────────────────────────

def gg_ent(p) -> str:
    arr = p["properties"].get("Entreprise", {}).get("title", [])
    return arr[0]["plain_text"].strip() if arr else ""

def gg_ref(p) -> str:
    arr = p["properties"].get("Référence Offre", {}).get("rich_text", [])
    return arr[0]["plain_text"].strip() if arr else ""

def gg_poste(p) -> str:
    arr = p["properties"].get("Intitulé Poste", {}).get("rich_text", [])
    return arr[0]["plain_text"].strip() if arr else ""


# ── Recherche par référence ou par nom ────────────────────────────────────────

def find_by_ref(pages: list, ref: str) -> list:
    return [p for p in pages if gg_ref(p) == ref]

def find_by_name(pages: list, name: str) -> list:
    return [p for p in pages if norm(gg_ent(p)) == norm(name)]


# ── Gestion des options select (idempotent) ───────────────────────────────────

def ensure_select_options(db_id: str, prop_name: str, new_options: list[str]):
    """Ajoute les options manquantes à une propriété Select sans écraser les existantes."""
    db_data  = requests.get(f"{API}/databases/{db_id}", headers=HDRS).json()
    existing = {
        o["name"]
        for o in db_data.get("properties", {})
                        .get(prop_name, {})
                        .get("select", {})
                        .get("options", [])
    }
    to_add = [{"name": o} for o in new_options if o not in existing]
    if not to_add:
        return
    patch(f"databases/{db_id}", {
        "properties": {
            prop_name: {
                "select": {
                    "options": list({"name": o["name"]} for o in
                                    db_data["properties"][prop_name]["select"]["options"])
                             + to_add
                }
            }
        }
    })


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURER ICI : vos mises à jour du jour
# ══════════════════════════════════════════════════════════════════════════════

UPDATES = [
    # {
    #   "db":        GG_DB,                # PME_DB ou GG_DB
    #   "find_by":   "ref",                # "ref" ou "name"
    #   "key":       "2026-XXXXX",         # valeur de recherche
    #   "props": {
    #       "Statut":          p_select("Rejetée"),
    #       "Notes":           p_text("Rejet reçu le JJ/MM de contact@entreprise.fr."),
    #       "Date Traitement": p_date("2026-MM-JJ"),
    #   },
    # },
]

CREATES = [
    # {
    #   "db":     GG_DB,
    #   "ent":    "Nom Entreprise",
    #   "poste":  "Alternance — Data Analyst / Scientist",
    #   "ref":    "2026-XXXXX",       # optionnel
    #   "statut": "Rejetée",
    #   "date":   "2026-MM-JJ",
    #   "email":  "contact@entreprise.fr",   # optionnel
    #   "notes":  "Rejet reçu le JJ/MM.",
    # },
]


# ══════════════════════════════════════════════════════════════════════════════
# MAIN — ne pas modifier
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("NOTION — Mise à jour quotidienne")
    print("=" * 60)

    # Charger les deux bases une seule fois
    print("\nChargement des bases...")
    pme_pages = load_pages(PME_DB) if PME_DB else []
    gg_pages  = load_pages(GG_DB)  if GG_DB  else []
    print(f"  PME : {len(pme_pages)} pages | GG : {len(gg_pages)} pages")

    errors, updated, created = [], [], []

    # ── UPDATES ───────────────────────────────────────────────────────────────
    for u in UPDATES:
        db_id  = u["db"]
        pages  = pme_pages if db_id == PME_DB else gg_pages
        key    = u["key"]
        by     = u.get("find_by", "name")

        hits = find_by_ref(pages, key) if by == "ref" else find_by_name(pages, key)

        if not hits:
            errors.append(f"UPDATE {key} — introuvable")
            continue
        if len(hits) > 1:
            errors.append(f"UPDATE {key} — {len(hits)} entrées ambiguës")
            continue

        patch(f"pages/{hits[0]['id']}", {"properties": u["props"]})
        updated.append(key)
        print(f"  ✅ MAJ {key}")
        time.sleep(0.4)

    # ── CREATES ───────────────────────────────────────────────────────────────
    for e in CREATES:
        db_id    = e["db"]
        pages    = pme_pages if db_id == PME_DB else gg_pages
        ent_name = e["ent"]
        ref      = e.get("ref", "")

        # Vérification doublon
        dup = find_by_ref(pages, ref) if ref else find_by_name(pages, ent_name)
        if dup:
            errors.append(f"CREATE {ent_name} {ref} — doublon, skipped")
            continue

        props = {
            "Entreprise":      p_title(ent_name),
            "Intitulé Poste":  p_text(e.get("poste", "")),
            "Statut":          p_select(e.get("statut", "Envoyée")),
            "Date Traitement": p_date(e.get("date", "")),
            "Notes":           p_text(e.get("notes", "")),
        }
        if ref:
            props["Référence Offre"] = p_text(ref)
        if e.get("email"):
            props["Contact Email"] = p_email(e["email"])

        post("pages", {"parent": {"database_id": db_id}, "properties": props})
        created.append(f"{ent_name} {ref}".strip())
        print(f"  ✅ CRÉÉ {ent_name} {ref}")
        time.sleep(0.4)

    # ── Résumé ────────────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"  Mis à jour : {len(updated)}  |  Créés : {len(created)}  |  Erreurs : {len(errors)}")
    for er in errors:
        print(f"    ❌ {er}")
    print("=" * 60)


if __name__ == "__main__":
    main()

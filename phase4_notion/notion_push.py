#!/usr/bin/env python3
"""
Notion Push — lm_tracker.csv → base de données Notion
Utilise l'API HTTP directe (Notion-Version: 2022-06-28).
Usage : python notion_push.py
"""

import csv
import json
import time
import sys
import requests

import os
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
PAGE_ID      = os.environ.get("NOTION_PARENT_PAGE_ID", "")
INPUT_CSV    = "lm_tracker.csv"
BATCH_SIZE   = 10
BATCH_DELAY  = 0.5
API_BASE     = "https://api.notion.com/v1"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def api(method: str, path: str, body: dict = None) -> dict:
    url = f"{API_BASE}/{path}"
    r = getattr(requests, method)(url, headers=HEADERS, json=body, timeout=20)
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code} {path}: {r.text[:200]}")
    return r.json()


def val(row: dict, key: str) -> str:
    v = row.get(key, "")
    return str(v).strip() if v and str(v).strip() not in ("nan", "None", "") else ""


# ── Création base de données ──────────────────────────────────────────────────

def create_database() -> tuple[str, str]:
    print("Création de la base de données...")
    body = {
        "parent": {"type": "page_id", "page_id": PAGE_ID},
        "title": [{"type": "text", "text": {"content": "🎯 Candidatures Data — Alternance 2026"}}],
        "properties": {
            "Nom": {"title": {}},
            "Score": {
                "select": {"options": [
                    {"name": "A", "color": "green"},
                    {"name": "B", "color": "blue"},
                    {"name": "C", "color": "orange"},
                    {"name": "D", "color": "gray"},
                ]}
            },
            "Vertical": {
                "select": {"options": [
                    {"name": "ESN / Informatique",  "color": "purple"},
                    {"name": "Conseil / BI",        "color": "blue"},
                    {"name": "Fintech / Assurance", "color": "green"},
                    {"name": "Retail / E-com",      "color": "yellow"},
                    {"name": "Startup / Scale-up",  "color": "red"},
                ]}
            },
            "CV Version": {
                "select": {"options": [
                    {"name": "CV_DataScientist", "color": "purple"},
                    {"name": "CV_DataAnalyst",   "color": "blue"},
                ]}
            },
            "Email":         {"email": {}},
            "Page Carrière": {"url": {}},
            "Site Web":      {"url": {}},
            "Envoyé":        {"date": {}},
            "Réponse": {
                "select": {"options": [
                    {"name": "En attente", "color": "gray"},
                    {"name": "Positive",   "color": "green"},
                    {"name": "Négative",   "color": "red"},
                    {"name": "Relance",    "color": "yellow"},
                ]}
            },
            "Relance J+10": {"date": {}},
            "Notes":        {"rich_text": {}},
        },
    }
    db = api("post", "databases", body)
    db_id  = db["id"]
    db_url = db.get("url", f"https://notion.so/{db_id.replace('-', '')}")
    print(f"  ✅ Base créée — {len(db.get('properties', {}))} propriétés")
    print(f"  URL : {db_url}")
    return db_id, db_url


# ── Construction d'une page Notion ────────────────────────────────────────────

def build_page(db_id: str, row: dict) -> dict:
    props = {
        "Nom": {"title": [{"text": {"content": val(row, "nom") or "(sans nom)"}}]},
    }

    if v := val(row, "score"):
        props["Score"] = {"select": {"name": v}}

    if v := val(row, "vertical"):
        props["Vertical"] = {"select": {"name": v}}

    if v := val(row, "cv_version"):
        props["CV Version"] = {"select": {"name": v}}

    if v := val(row, "email"):
        props["Email"] = {"email": v}

    if v := val(row, "page_carriere"):
        props["Page Carrière"] = {"url": v}

    if v := val(row, "url_resolue"):
        props["Site Web"] = {"url": v}

    if v := val(row, "envoye"):
        props["Envoyé"] = {"date": {"start": v}}

    if v := val(row, "reponse"):
        props["Réponse"] = {"select": {"name": v}}

    if v := val(row, "relance_j10"):
        props["Relance J+10"] = {"date": {"start": v}}

    if v := val(row, "notes"):
        props["Notes"] = {"rich_text": [{"text": {"content": v[:2000]}}]}

    return {"parent": {"database_id": db_id}, "properties": props}


# ── Push par batches ──────────────────────────────────────────────────────────

def push_rows(db_id: str, rows: list[dict]) -> tuple[int, int]:
    total, success, errors = len(rows), 0, 0

    for i in range(0, total, BATCH_SIZE):
        batch = rows[i: i + BATCH_SIZE]

        for row in batch:
            try:
                api("post", "pages", build_page(db_id, row))
                success += 1
            except Exception as e:
                print(f"  ⚠️  {val(row,'nom')[:40]} : {str(e)[:100]}")
                errors += 1

        done = min(i + BATCH_SIZE, total)
        if done % 20 == 0 or done == total:
            print(f"  [{done}/{total}] — {success} OK, {errors} erreurs")

        if i + BATCH_SIZE < total:
            time.sleep(BATCH_DELAY)

    return success, errors


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("NOTION PUSH — Candidatures Data Alternance 2026")
    print("=" * 55)

    # Lecture CSV
    rows = []
    with open(INPUT_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"\n📂 {len(rows)} lignes chargées depuis {INPUT_CSV}")

    # Test connexion
    try:
        me = api("get", "users/me")
        print(f"   Connecté : {me.get('name', me.get('id', '?'))}")
    except Exception as e:
        print(f"❌ Connexion Notion échouée : {e}")
        sys.exit(1)

    # Création DB
    db_id, db_url = create_database()
    time.sleep(1)  # laisse Notion indexer les propriétés

    # Push
    print(f"\nPush de {len(rows)} entrées (batch={BATCH_SIZE}, délai={BATCH_DELAY}s)...")
    success, errors = push_rows(db_id, rows)

    # Rapport final
    print(f"\n{'=' * 55}")
    print(f"✅ TERMINÉ — {success} pages créées, {errors} erreurs")
    print(f"\n🔗 Base de données :")
    print(f"   {db_url}")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    main()

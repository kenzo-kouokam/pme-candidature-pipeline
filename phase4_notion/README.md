# Phase 4 — CRM Notion

> **Objectif :** centraliser toutes les candidatures dans deux bases de données Notion maintenues automatiquement — push initial des 211 PMEs et mises à jour quotidiennes basées sur la surveillance email.

---

## Pourquoi Notion comme CRM ?

Notion permet de voir toutes les candidatures en vue tableau (filtrable par statut, vertical, date), d'ajouter des notes par ligne, et d'y accéder depuis n'importe quel appareil. L'API REST officielle (version `2022-06-28`) permet de créer et modifier des pages programmatiquement.

L'alternative aurait été une feuille Google Sheets — mais Sheets ne gère pas les propriétés typées (Select, Date, Email, URL), ce qui rendrait le filtrage et les vues beaucoup moins efficaces.

---

## Pourquoi l'API HTTP directe et pas un SDK ?

Le SDK Python officiel de Notion (`notion-client`) ne supporte pas correctement la **création de propriétés de base de données** au moment de la création. Il gère la lecture et l'écriture de pages, mais pas le schéma initial complet.

En passant par `requests` en HTTP pur avec l'en-tête `Notion-Version: 2022-06-28`, on a un contrôle total sur le payload JSON envoyé — y compris les options des champs `select` (couleurs, noms) et les types de propriétés exotiques.

```python
HDRS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
```

---

## Les deux bases

### Base PME — candidatures spontanées (`notion_push.py`)

Créée programmatiquement par `notion_push.py` dans une page Notion parente (spécifiée par `NOTION_PARENT_PAGE_ID`). Propriétés :

| Propriété | Type | Usage |
|---|---|---|
| `Nom` | Titre | Nom de l'entreprise |
| `Score` | Select | A / B / C / D (Phase 2) |
| `Vertical` | Select | ESN, Conseil, Fintech, Retail, Startup |
| `CV Version` | Select | CV_DataScientist / CV_DataAnalyst |
| `Email` | Email | Email RH de contact |
| `Page Carrière` | URL | Lien page recrutement |
| `Site Web` | URL | URL officielle |
| `Envoyé` | Date | Date d'envoi |
| `Réponse` | Select | En attente / Positive / Négative / Relance |
| `Relance J+10` | Date | Date relance automatique |
| `Notes` | Rich text | Notes libres |

**211 pages créées en batches de 10** avec délai de 0.5s entre batches (respect des rate limits Notion).

### Base Grands Groupes — offres ciblées

Alimentée par les scripts de mise à jour quotidiens. Propriétés complémentaires :
- `Entreprise` (titre), `Intitulé Poste`, `Référence Offre`, `Statut`, `Contact Email`, `Date Traitement`, `Notes`

Cette base suit les candidatures sur offres publiées (LinkedIn, APEC, Welcome to the Jungle) avec leurs références uniques.

---

## Logique de mise à jour quotidienne (`notion_update_template.py`)

### Le problème du doublon

Plusieurs entreprises du CAC40 publient plusieurs offres data simultanément (ex: Airbus avec 3 offres JR10394399, JR10397924, JR10414724). Si on cherche uniquement par nom, la 2ème offre est bloquée en "doublon". La logique correcte :

```
1. Chercher par référence d'offre (unique par offre)
   → Si trouvé : c'est la bonne entrée → update ou skip
   
2. Si pas de référence : chercher par nom normalisé
   → Si trouvé : potentiel doublon → skip avec log
   → Si pas trouvé : création autorisée
```

```python
def find_by_ref(pages, ref):
    return [p for p in pages if gg_ref(p) == ref]

def find_by_name(pages, name):
    return [p for p in pages if norm(gg_ent(p)) == norm(name)]
```

### Normalisation des noms

Les accents et la casse créent des faux non-matchs. "Société Générale" ≠ "societe generale" pour Python. La normalisation Unicode résout ça :

```python
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.lower().strip()
```

`NFKD` décompose les caractères composés (é → e + ́) puis l'encodage ASCII avec `ignore` supprime les diacritiques. Le résultat est un slug ASCII minuscule comparable sans risque.

### Pagination complète

L'API Notion retourne au maximum 100 résultats par requête. Pour une base de 200+ pages, il faut paginer explicitement :

```python
def load_pages(db_id):
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
```

Sans pagination, on travaille sur un snapshot incomplet de la base — et les doublons passent au travers.

### Idempotence des options Select

L'API Notion lève une erreur si on tente d'utiliser un Select avec une valeur qui n'existe pas encore dans les options définies. Pour ajouter de nouveaux statuts (ex : "Entretien réalisé — 2nd tour en attente") sans écraser les options existantes :

```python
def ensure_select_options(db_id, prop_name, new_options):
    db_data  = requests.get(f"{API}/databases/{db_id}", headers=HDRS).json()
    existing = {o["name"] for o in db_data["properties"][prop_name]["select"]["options"]}
    to_add   = [{"name": o} for o in new_options if o not in existing]
    if to_add:
        # PATCH le schéma avec les nouvelles options ajoutées
        patch(f"databases/{db_id}", { "properties": { prop_name: { "select": {
            "options": [...existing_as_objects] + to_add
        }}}})
```

Cette fonction est appelée en début de chaque script quotidien pour les statuts non-standards.

### Workflow de veille email

```
Gmail + Outlook
      │
      ├─ Recherche : "candidature" OR "alternance" OR "entretien" OR "rejet"
      │
      ├─ Pour chaque thread non-lu :
      │     ├─ Lecture du corps complet (les objets seuls sont ambigus)
      │     ├─ Identification entreprise (nom dans l'objet ou le corps)
      │     ├─ Cross-référencement Notion (PME ou GG ? ref connue ?)
      │     └─ Classification : Rejetée / Entretien planifié / Réponse positive
      │
      └─ Génération script notion_updates_JJMOIS.py → exécution
```

---

## Utiliser le template

```bash
# Copier le template pour la session du jour
cp phase4_notion/notion_update_template.py notion_updates_JJMOIS.py

# Éditer le fichier : remplir UPDATES et CREATES
# UPDATES = liste de mises à jour (statut, notes, date)
# CREATES = liste de nouvelles entrées (nouvelles candidatures ou rejets)

python notion_updates_JJMOIS.py
```

### Exemple UPDATES

```python
UPDATES = [
    {
        "db":      GG_DB,
        "find_by": "ref",
        "key":     "2026-112793",   # Référence offre Amundi
        "props": {
            "Statut": p_select("Entretien réalisé — suite en attente"),
            "Notes":  p_text("Entretien technique réalisé le 02/07. Retour sous 2 semaines."),
        },
    },
]
```

### Exemple CREATES

```python
CREATES = [
    {
        "db":     GG_DB,
        "ent":    "BlaBlaCar",
        "poste":  "Carpool Pricing Analyst Apprentice",
        "ref":    "",
        "statut": "Rejetée",
        "date":   "2026-07-02",
        "notes":  "Rejet reçu le 02/07 de Chloé FRIESS (chloe.friess@blablacar.com).",
    },
]
```

---

## Variables d'environnement requises

```bash
NOTION_TOKEN=ntn_xxxx              # Token d'intégration Notion
NOTION_PARENT_PAGE_ID=xxxx-xxxx    # ID de la page parente (push initial)
NOTION_PME_DB_ID=xxxx-xxxx         # ID base PME (candidatures spontanées)
NOTION_GG_DB_ID=xxxx-xxxx          # ID base Grands Groupes
```

Voir `.env.example` à la racine.

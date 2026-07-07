# Phase 1 — Scraping multi-sources

> **Objectif :** constituer une liste brute de PMEs tech/data en Île-de-France, issues de trois sources croisées, avec un maximum d'informations disponibles dès le départ.

---

## Pourquoi trois sources ?

Aucune source unique ne suffit pour cartographier le tissu PME français :

| Source | Ce qu'elle apporte | Limites |
|---|---|---|
| **API gouvernementale** (recherche-entreprises.api.gouv.fr) | Données SIRENE officielles — NAF exact, taille réelle, SIREN, adresse | Pas d'URL site ni d'email |
| **PagesJaunes** | URL du site web directe (via décodage base64), présence réelle | Secteur moins précis, risque de biais commerçants locaux |
| **Kompass** | Effectif déclaré, secteur industriel, couverture B2B solide | Sélecteurs CSS instables selon les pages |

Croiser les trois permet d'avoir à la fois la **fiabilité légale** (SIRENE), l'**URL directe** (PagesJaunes) et la **couverture B2B** (Kompass). La déduplication finale sur le nom garantit l'unicité.

---

## Ciblage — codes NAF et taille

### Pourquoi les codes NAF ?

L'API SIRENE classe chaque entreprise selon son activité principale (code NAF APE). C'est le filtre le plus précis pour éviter de scraper des PMEs hors-scope (boulangeries, plombiers, etc.).

```python
NAF_CODES = [
    "62.01Z",  # Programmation informatique
    "62.02A",  # Conseil en systèmes et logiciels
    "62.09Z",  # Autres activités informatiques
    "63.11Z",  # Traitement de données, hébergement
    "63.12Z",  # Portails Internet
    "70.22Z",  # Conseil pour les affaires et gestion
    "66.19B",  # Aux. services financiers (fintech)
    "64.99Z",  # Intermédiations monétaires
    ...
]
```

### Pourquoi 20-250 salariés ?

- **< 20** : micro-entreprises sans alternance structurée dans la majorité des cas
- **> 250** : grands comptes → postent leurs offres sur LinkedIn/APEC (campagne ciblée séparée)
- **20-250** : le sweet spot PME — besoin de compétences data réel, processus de recrutement moins formalisé, concurrence faible sur les candidatures spontanées

Les tranches INSEE retenues : `12` (20-49), `21` (50-99), `22` (100-199), `31` (200-249).

---

## Sélecteurs PagesJaunes — décodage base64

PagesJaunes encode les URLs de sites web en base64 dans un attribut `data-pjlb` pour éviter le scraping direct. Structure découverte sur le HTML réel (juin 2025) :

```html
<a class="btn_external_link" data-pjlb='{"url":"aHR0cHM6Ly93d3cuZXhhbXBsZS5jb20=","ucod":"b64u8"}'>
```

```python
def _decode_pjlb(el) -> str | None:
    raw = el.get("data-pjlb", "")
    data = json.loads(raw)
    b64  = data.get("url", "")
    return base64.b64decode(b64 + "==").decode("utf-8", errors="ignore")
```

Le padding `+ "=="` est nécessaire car PagesJaunes ne padde pas systématiquement ses chaînes base64.

---

## Anti-blocage

Le scraping web sans précautions déclenche rapidement des codes 429 ou des captchas.

```
Délai aléatoire : 2.5 – 5.5 secondes entre chaque requête
User-Agents    : rotation parmi 4 UA (Chrome Mac/Win, Firefox Linux, Safari)
Session        : réinitialisation entre secteurs (nouveau User-Agent)
Détection 429  : pause forcée 45 secondes puis retry
Détection captcha : log + passage au secteur suivant (pas de blocage infini)
```

L'aléatoire dans les délais est intentionnel — un délai fixe est plus facilement détecté que des intervalles variables.

---

## Déduplication

Une même entreprise peut apparaître dans les 3 sources. La déduplication se fait sur le nom normalisé (`.str.title()`) en gardant la ligne la plus riche :

```python
df["_score"] = (
    df["url_site"].notna().astype(int)   # +1 si URL site connue
    + df["siren"].notna().astype(int)    # +1 si SIREN disponible
    + df["taille"].notna().astype(int)   # +1 si effectif connu
)
df = df.sort_values("_score", ascending=False)
df = df.drop_duplicates(subset=["nom"], keep="first")
```

---

## Output

Fichier : `entreprises_brut.csv`

| Colonne | Description |
|---|---|
| `nom` | Nom normalisé (`.title()`) |
| `secteur` | Code NAF ou secteur PJ/Kompass |
| `url_site` | URL directe si disponible (PJ ou Kompass) |
| `adresse` | Commune ou "Île-de-France" |
| `taille` | Tranche INSEE ou effectif déclaré |
| `siren` | SIREN officiel (API seulement) |
| `url_societe` | URL profil PagesJaunes (fallback Phase 2) |
| `source` | `API_officielle` / `PagesJaunes` / `Kompass` |

**Résultat obtenu : 656 PMEs uniques**

---

## Usage

```bash
pip install -r requirements.txt
python phase1_scraper/scraper_phase1.py
# Durée : ~20-30 min (délais anti-blocage inclus)
# Output : entreprises_brut.csv à la racine
```

→ Étape suivante : [`phase2_enrichissement/`](../phase2_enrichissement/README.md)

# Phase 3 — Nettoyage & génération LM

> **Objectif :** filtrer les faux positifs de la Phase 2, classer chaque entreprise dans un vertical sectoriel, puis générer une lettre de motivation personnalisée pour chacune des 211 entreprises retenues.

---

## 3A — Nettoyage (`nettoyage_phase3a.py`)

La Phase 2 enrichit sans juger. La Phase 3A juge : elle rejette tout ce qui ne correspond pas à une vraie PME data/tech contactable.

### Les 5 filtres dans l'ordre

**Filtre 1 — Score C/D**

On ne garde que les entreprises avec un email direct ou une page carrière (scores A et B). Les C et D n'offrent pas de canal de contact précis pour une candidature spontanée efficace.

**Filtre 2 — Statut non-`ok`**

Si le scraping a échoué (`url_introuvable`, `site_inaccessible`, `erreur: ...`), l'entrée est rejetée. Aucune information fiable n'est disponible.

**Filtre 3 — Nom d'entreprise connu comme grande structure**

La Phase 1 a pu remonter des grandes entreprises qui se déclarent sous des codes NAF PME (certaines ESN et cabinets de conseil filiales). Un filtre regex sur le nom élimine les cas reconnus :

```python
NOMS_FP = re.compile(
    r"\b(ernst.?young|ey\b|kpmg|deloitte|pwc|accenture|capgemini|"
    r"bouygues|orange|sfr|total|lvmh|bnp paribas|google\b|apple\b|microsoft\b)\b",
    re.IGNORECASE,
)
```

**Filtre 4 — Email placeholder**

Certains sites affichent des exemples d'emails dans leur HTML (`you@domain.com`, `nomprenom@entreprise.fr`). Ces faux emails seraient des adresses invalides si on les utilisait.

**Filtre 5 — URL résolue incohérente**

Si le domaine résolu par DuckDuckGo appartient à un Big 4 (`ey.com`, `kpmg.com`, `deloitte.com`...), à une plateforme générique, ou a un TLD étranger non-francophone (`.no`, `.de`, `.uk`...), l'entreprise est rejetée. Cela arrive quand DDG retourne le site du groupe international plutôt que la filiale française.

---

## Mapping vertical

Chaque entreprise cible est classée dans un des 5 verticaux sectoriels qui détermine quel template de LM elle recevra.

### Priorité : code NAF d'abord

Les entreprises issues de l'API gouvernementale ont un code NAF précis :

| Code NAF | Vertical |
|---|---|
| 62.01Z, 62.02A, 62.09Z, 63.11Z, 63.12Z | ESN / Informatique |
| 70.22Z, 70.21Z | Conseil / BI |
| 66.19B, 64.99Z | Fintech / Assurance |
| 58.13Z, 59.12Z, 60.20Z | Retail / E-com |

### Fallback : mots-clés sur le secteur PagesJaunes/Kompass

Pour les entreprises sans code NAF, le secteur textuel est analysé :
```python
if any(k in sl for k in ["fintech", "assurance", "finance"]):
    return "Fintech / Assurance"
if any(k in sl for k in ["e-commerce", "retail", "media", "commerce"]):
    return "Retail / E-com"
...
```

Chaque vertical est aussi associé à une recommandation de version CV :
- `CV_DataScientist` pour ESN, Fintech, Startup (ML en tête)
- `CV_DataAnalyst` pour Conseil et Retail (BI/SQL en tête)

---

## 3C — Génération LM (`lm_generator.py`)

### Architecture : template + intro dynamique

Chaque LM est construite en deux parties :

```
templates/template_[vertical].txt
        │
        │  Contient {intro_personnalise} et {entreprise}
        │  → corps fixe du discours (expériences, stack, disponibilité)
        │
generate_intro(nom, vertical, url, page_carriere)
        │
        │  Génère 2 phrases spécifiques à l'entreprise
        │  Phrase 1 : signal sur le positionnement de l'entreprise
        │  Phrase 2 : lien avec le profil data du candidat
        │
        ▼
lm_generees/{slug}.txt
```

### Génération de l'intro — sans API externe

L'intro est générée localement par sélection déterministe dans des pools de phrases pré-écrites par vertical. Le principe : chaque vertical a 3 variantes de phrase 1 et 2, et l'index est choisi selon la somme des codes ASCII du nom de l'entreprise modulo le nombre de variantes.

```python
idx = sum(ord(c) for c in nom) % len(p1_list)
p1 = p1_list[idx]
p2 = p2_list[idx % len(p2_list)]
```

Cela garantit que :
- **Deux entreprises différentes** reçoivent des introductions différentes (pas de copier-coller visible)
- **La même entreprise** reçoit toujours la même intro (reproductibilité si relance)
- **Pas de dépendance réseau** ni de coût API pour la génération

Si une page carrière est disponible, l'intro l'indique explicitement — ce signal renforce la crédibilité de la candidature ("j'ai vu que vous recrutez").

### Les 5 templates

| Fichier | Vertical | Ton dominant |
|---|---|---|
| `template_esn_informatique.txt` | ESN / Informatique | Technique, production ML, livrables |
| `template_conseil_bi.txt` | Conseil / BI | Analytique, BI, décisionnel, SQL/Power BI |
| `template_fintech_assurance.txt` | Fintech / Assurance | Quantitatif, scoring, risque, SHAP |
| `template_retail_ecom.txt` | Retail / E-com | E-commerce, catalogue, comportements d'achat |
| `template_startup_scaleup.txt` | Startup / Scale-up | Autonomie, end-to-end, croissance rapide |

Chaque template suit le même squelette (objet, intro personnalisée, profil candidat, 3 projets structurants, stack, disponibilité, formule de politesse) mais adapte le vocabulaire et les exemples au secteur.

### Slug de nom de fichier

Chaque LM est sauvegardée sous `lm_generees/{slug}.txt` où `slug` est le nom normalisé :

```python
def slug(nom: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", nom.lower().strip())
    return s[:50].strip("_")
```

Exemple : `"Société DataLab & Partners"` → `societe_datalab_partners.txt`

### Reprise automatique

Si le script est relancé, il lit `lm_tracker.csv` pour identifier les slugs déjà générés et les saute. Aucune LM n'est regénérée deux fois.

---

## Output

```
phase3_generation/
├── nettoyage_phase3a.py     → entreprises_cibles.csv (211)
│                            → entreprises_rejetees.csv (audit)
├── lm_generator.py          → lm_generees/*.txt (211 fichiers)
│                            → lm_tracker.csv (suivi envois)
└── templates/
    ├── template_esn_informatique.txt
    ├── template_conseil_bi.txt
    ├── template_fintech_assurance.txt
    ├── template_retail_ecom.txt
    └── template_startup_scaleup.txt
```

`lm_tracker.csv` sert de CRM léger pour l'envoi : colonnes `envoye`, `reponse`, `relance_j10`, `notes` à remplir au fil des envois.

---

## Usage

```bash
# 3A — Nettoyage (< 1 min)
python phase3_generation/nettoyage_phase3a.py
# Lit : entreprises_enrichi.csv
# Écrit : entreprises_cibles.csv + entreprises_rejetees.csv

# 3C — Génération (≈ 5-10 min)
python phase3_generation/lm_generator.py
# Lit : entreprises_cibles.csv + templates/*.txt
# Écrit : lm_generees/*.txt + lm_tracker.csv
```

→ Étape suivante : [`phase4_notion/`](../phase4_notion/README.md)

<div align="center">

# pme-candidature-pipeline

<p>
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Notion_API-2022--06--28-000000?style=flat-square&logo=notion&logoColor=white" />
  <img src="https://img.shields.io/badge/DuckDuckGo_Search-DE5833?style=flat-square&logo=duckduckgo&logoColor=white" />
  <img src="https://img.shields.io/badge/Pandas-150458?style=flat-square&logo=pandas&logoColor=white" />
  <img src="https://img.shields.io/badge/BeautifulSoup4-43B02A?style=flat-square" />
  <img src="https://img.shields.io/badge/Gmail_+_Outlook-scanning-EA4335?style=flat-square&logo=gmail&logoColor=white" />
</p>

<p>
  <img src="https://img.shields.io/badge/PMEs_scrapées-656-4CAF50?style=flat-square" />
  <img src="https://img.shields.io/badge/LM_générées-211-2196F3?style=flat-square" />
  <img src="https://img.shields.io/badge/Grands_Groupes_suivis-160+-FF9800?style=flat-square" />
  <img src="https://img.shields.io/badge/Bases_Notion-2-9C27B0?style=flat-square" />
</p>

**Pipeline end-to-end de recherche d'alternance — du scraping de PME à la gestion de candidatures dans Notion, avec surveillance automatique des boîtes mail.**

</div>

---

## Contexte

En M2 Data Science & BI à Epitech Toulouse, je cherchais une alternance de 12 mois dès septembre 2026. Le marché de l'alternance data est saturé sur les grands groupes — tous les étudiants postulent aux mêmes offres LinkedIn. J'ai choisi une approche différente : cibler les **PME tech/data d'Île-de-France** par candidatures spontanées, là où la concurrence est quasi-nulle.

## Le problème

Il n'existe aucune source structurée listant les PMEs françaises avec leurs contacts RH. Pour envoyer 200 candidatures spontanées ciblées, il faut :

1. **Identifier** les entreprises (secteur, taille, localisation)
2. **Enrichir** chaque entreprise avec son site web, son email RH, sa page recrutement
3. **Personnaliser** chaque lettre de motivation au secteur de l'entreprise
4. **Centraliser** toutes les candidatures dans un CRM
5. **Suivre** les réponses en scannant ses boîtes mail chaque jour

Faire tout ça manuellement : 50-80 heures de travail. L'automatiser : un week-end de code.

## La solution

Un pipeline Python en 4 phases enchaînées, avec un CRM Notion alimenté automatiquement et un système de veille email quotidien.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ALTERNANCE PIPELINE                          │
└─────────────────────────────────────────────────────────────────────┘

  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
  │   PHASE 1    │    │   PHASE 2    │    │   PHASE 3    │    │   PHASE 4    │
  │  SCRAPING    │───▶│ ENRICHISSEMENT│───▶│  GÉNÉRATION  │───▶│    NOTION    │
  │              │    │              │    │     LM       │    │     PUSH     │
  └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
         │                   │                   │                   │
  3 sources            DuckDuckGo          5 templates          API REST
  API gov.fr           URL resolve         par vertical         HTTP direct
  PagesJaunes          Email extract       intro générée        Batch push
  Kompass              Career page         personnalisée
  12 NAF codes         Score A/B/C/D       211 LM .txt
  656 PMEs             Dédup                                         │
                                                               ┌─────▼──────┐
                                                               │   CRM PME  │
                                                               │  211 pages │
                                                               └────────────┘

  ┌──────────────────────────────────────────────────────────────────────────┐
  │                        PHASE 5 — VEILLE QUOTIDIENNE                      │
  │                                                                          │
  │  Gmail ──────┐                                                           │
  │               ├──▶ Scan candidature/rejet/entretien ──▶ notion_update.py │
  │  Outlook ────┘                                                           │
  │                                                          ┌───────────────┐│
  │                           + Grands Groupes ─────────────▶│  CRM GG 160+ ││
  │                             (offres ciblées)             └───────────────┘│
  └──────────────────────────────────────────────────────────────────────────┘
```

## Résultats

| Métrique | Valeur |
|---|---|
| PMEs identifiées (Phase 1) | 656 |
| PMEs retenues après scoring A/B (Phase 3) | 211 |
| Lettres de motivation générées | 211 |
| Temps moyen de génération par LM | < 3 secondes |
| Grands groupes suivis en parallèle | 160+ |
| Pages Notion créées automatiquement | 370+ |
| Scripts de mise à jour quotidiens | 10+ |
| Faux positifs filtrés (Big 4, plateformes) | 100+ |

## Compétences mobilisées

| Domaine | Compétence | Application |
|---|---|---|
| **Web scraping** | BeautifulSoup4, lxml | PagesJaunes, Kompass — sélecteurs CSS, décodage base64 |
| **API REST** | `requests` | API gouv. SIRENE, Notion API (CREATE/PATCH/QUERY) |
| **Search automation** | DuckDuckGo Search | Résolution URL entreprise, filtre liste noire domaines |
| **Data engineering** | pandas | Déduplication, scoring, tri multicritère, export CSV |
| **NLP basique** | `unicodedata`, regex | Normalisation accents, matching flou noms entreprise |
| **Pipeline design** | Python pur | Reprise sur erreur, sauvegarde incrémentale, logs structurés |
| **CRM automation** | Notion API v2022-06-28 | Pagination, idempotence selects, gestion doublons par ref |
| **Email monitoring** | Gmail API, Outlook API | Scan candidatures, détection rejets, mise à jour auto |

## Les 5 phases en détail

### Phase 1 — Scraping multi-sources (`phase1_scraper/`)

Trois sources croisées pour maximiser la couverture PME :

- **API gouvernementale** (`recherche-entreprises.api.gouv.fr`) — données SIRENE officielles. Filtrage par 12 codes NAF (62.01Z, 70.22Z, 66.19B...) × 8 départements IDF × tranches d'effectif 20-250 salariés. Aucune clé API requise.
- **PagesJaunes** — scraping par secteur avec décodage des URLs base64 (`data-pjlb`). Rotation User-Agent, détection captcha, gestion 429.
- **Kompass** — scraping sélecteurs multi-candidats (la structure HTML varie selon les pages).

Déduplication finale sur le nom, avec priorité aux lignes contenant le plus d'informations (URL + SIREN + taille).

**Output :** `entreprises_brut.csv` — 656 PMEs

### Phase 2 — Enrichissement (`phase2_enrichissement/`)

Pour chaque PME, résolution de l'URL de son site officiel puis scraping :

1. **Résolution URL** : utilise l'URL directe si disponible → sinon visite le profil PagesJaunes (décodage base64) → sinon requête DuckDuckGo avec liste noire de 30+ domaines annuaires.
2. **Extraction email** : `mailto:` d'abord, puis regex sur le HTML brut. Priorité aux emails `recrutement/rh/contact` sur `info@`.
3. **Détection page carrière** : matching mots-clés dans les liens nav (`recrutement`, `careers`, `rejoindre`...) puis test de patterns d'URL (`/carrieres`, `/jobs`...).
4. **Scoring A/B/C/D** :
   - `A` — email direct + page carrière (contact immédiat possible)
   - `B` — page carrière seule (candidature via formulaire)
   - `C` — email générique ou formulaire seul
   - `D` — rien trouvé (site inaccessible ou absent)

Reprise automatique sur interruption (skip des lignes déjà traitées). Sauvegarde incrémentale toutes les 10 lignes.

**Output :** `entreprises_enrichi.csv`

### Phase 3 — Nettoyage & génération LM (`phase3_generation/`)

**3A — Nettoyage :** filtre les faux positifs en 5 passes :
- Score C/D → rejeté
- Nom reconnu comme grande entreprise (KPMG, Capgemini, Orange...) → rejeté
- Domaine résolu appartenant à un Big 4 ou une plateforme média → rejeté
- TLD étranger non-francophone (`.no`, `.de`, `.uk`...) → rejeté
- Email placeholder (`noreply@`, `@example`) → nettoyé

Mapping vers 5 verticaux sectoriels et recommandation CV (`CV_DataScientist` vs `CV_DataAnalyst`).

**3C — Génération LM :** pour chaque entreprise cible, injection d'une intro personnalisée dans 1 des 5 templates métier. L'intro (2 phrases) est générée déterministement selon le vertical et le nom de l'entreprise — pas d'API externe requise.

```
entreprises_cibles.csv
        │
        ▼
  get_vertical()  ──▶  template_[vertical].txt
        │                       │
  generate_intro()              │
  (phrases P1 + P2              │
   selon vertical + nom) ───────┘
        │
        ▼
  lm_generees/{slug}.txt   +   lm_tracker.csv
```

**Output :** 211 LM dans `lm_generees/` + `lm_tracker.csv`

### Phase 4 — Push Notion (`phase4_notion/`)

**`notion_push.py`** — création de la base de données Notion depuis zéro via API REST pure (pas de SDK tiers qui bloque la création des propriétés). Push des 211 LM en batches de 10 avec délai configurable.

**`notion_update_template.py`** — pattern réutilisable pour les mises à jour quotidiennes :
- Chargement complet de la base avec pagination (`has_more` + `next_cursor`)
- Recherche par référence d'offre d'abord, puis par nom normalisé (gestion accents)
- Vérification doublon avant création (`find_by_ref` → `find_by_name`)
- Gestion idempotente des options Select (ajout sans écrasement)

### Phase 5 — Veille email quotidienne

Scan automatique Gmail + Outlook avec mots-clés candidature/rejet/entretien. Pour chaque email ambigu, lecture du thread complet, cross-référencement Notion, puis génération et exécution du script de mise à jour. Les cas complexes (multi-offres même entreprise, doublons par ref vs par nom) sont résolus par la logique de matching.

**Deux bases Notion en parallèle :**
- `PME` — 211 candidatures spontanées (colonne titre `Nom`, statut `Réponse`)
- `Grands Groupes` — 160+ offres ciblées LinkedIn/APEC (colonne `Entreprise`, statut `Statut`, champ `Référence Offre`)

## Stack technique

| Outil | Rôle |
|---|---|
| `requests` | Toutes les requêtes HTTP (scraping + Notion API) |
| `BeautifulSoup4` + `lxml` | Parsing HTML PagesJaunes / Kompass / sites entreprises |
| `duckduckgo-search` | Résolution URL sans clé API |
| `pandas` | Manipulation CSV, déduplication, scoring |
| `unicodedata` | Normalisation accents pour matching flou |
| Notion API v2022-06-28 | CRM — CREATE / PATCH / QUERY |
| Gmail API (MCP) | Scan boîte Gmail — search + read threads |
| Outlook API (MCP) | Scan boîte Outlook — search + read emails |

## Structure du projet

```
alternance-pipeline/
├── phase1_scraper/
│   └── scraper_phase1.py          # Sources : API gov, PagesJaunes, Kompass
├── phase2_enrichissement/
│   └── enrichissement_phase2.py   # URL resolve, email, page carrière, score A/B/C/D
├── phase3_generation/
│   ├── nettoyage_phase3a.py       # Filtre faux positifs, mappe verticaux
│   ├── lm_generator.py            # Génère 211 LM personnalisées
│   └── templates/
│       ├── template_esn_informatique.txt
│       ├── template_conseil_bi.txt
│       ├── template_fintech_assurance.txt
│       ├── template_retail_ecom.txt
│       └── template_startup_scaleup.txt
├── phase4_notion/
│   ├── notion_push.py             # Push initial 211 entrées → Notion
│   └── notion_update_template.py  # Pattern réutilisable pour MAJ quotidiennes
├── requirements.txt
├── .env.example
└── .gitignore
```

## Lancer en local

**Prérequis :** Python 3.11+, un token Notion avec accès en écriture à une page.

```bash
# 1. Cloner et installer
git clone https://github.com/kenzo-kouokam/alternance-pipeline.git
cd alternance-pipeline
pip install -r requirements.txt

# 2. Configurer les secrets
cp .env.example .env
# Éditer .env avec votre NOTION_TOKEN et les IDs de vos bases

# 3. Lancer le pipeline dans l'ordre

# Phase 1 — Scraping (≈ 20-30 min selon les délais anti-blocage)
python phase1_scraper/scraper_phase1.py
# → entreprises_brut.csv

# Phase 2 — Enrichissement (≈ 2-4h selon la taille du CSV)
python phase2_enrichissement/enrichissement_phase2.py
# → entreprises_enrichi.csv

# Phase 3A — Nettoyage (< 1 min)
python phase3_generation/nettoyage_phase3a.py
# → entreprises_cibles.csv + entreprises_rejetees.csv

# Phase 3C — Génération LM (≈ 5-10 min)
python phase3_generation/lm_generator.py
# → lm_generees/*.txt + lm_tracker.csv

# Phase 4 — Push Notion (≈ 5 min, batch de 10 avec délais)
python phase4_notion/notion_push.py
# → 211 pages créées dans votre base Notion
```

**Pour les mises à jour quotidiennes :**
```bash
cp phase4_notion/notion_update_template.py notion_updates_JJMOIS.py
# Remplir les sections UPDATES et CREATES dans le fichier
python notion_updates_JJMOIS.py
```

> **Note :** Les fichiers CSV générés (`entreprises_*.csv`, `lm_tracker.csv`, `lm_generees/`) sont ignorés par `.gitignore` — ils contiennent des données personnelles et des emails d'entreprises.

---

<div align="center">
  <a href="https://linkedin.com/in/enzo-kamhoua">LinkedIn</a> ·
  <a href="https://github.com/kenzo-kouokam">GitHub</a>
</div>

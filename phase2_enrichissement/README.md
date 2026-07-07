# Phase 2 — Enrichissement

> **Objectif :** transformer la liste brute de 656 PMEs en une base qualifiée avec site web résolu, email de contact, page carrière détectée, et un score de contactabilité A/B/C/D.

---

## Pourquoi un enrichissement en deux temps ?

La Phase 1 donne des noms d'entreprises, parfois un SIREN, rarement un site web direct. Pour envoyer une candidature spontanée, il faut au minimum une URL valide. On ne peut pas écrire à une entreprise dont on ne connaît pas le site.

L'enrichissement résout ce problème en chaîne : plusieurs stratégies de résolution URL, puis scraping du site pour extraire le contact RH.

---

## Chaîne de résolution URL

Pour chaque entreprise, trois tentatives dans l'ordre, du plus direct au plus coûteux :

```
entreprise
    │
    ├─ url_site déjà disponible (Phase 1) ?
    │       └─ OUI → on l'utilise directement
    │
    ├─ url_societe contient un profil PagesJaunes (/pros/...) ?
    │       └─ OUI → visite la fiche PJ et extrait le site via data-pjlb base64
    │
    ├─ url_societe est un vrai site (hors annuaires) ?
    │       └─ OUI → on l'utilise
    │
    └─ Aucune URL valide
            └─ DuckDuckGo : "{nom entreprise}" site officiel France
                    └─ Filtre 30+ domaines annuaires (LinkedIn, Societe.com, etc.)
                    └─ Retourne l'URL racine (scheme + netloc) si domaine valide
```

### Pourquoi DuckDuckGo et pas Google ?

Google Search API est payante et impose des quotas stricts. Bing API aussi. DuckDuckGo propose une API non-officielle gratuite (`duckduckgo-search`) sans clé, suffisante pour ce cas d'usage où on fait ~1 requête par entreprise avec un délai de 1-2s.

### La liste noire de domaines

Sans filtre, DuckDuckGo retourne souvent LinkedIn, Societe.com, PagesJaunes ou Manageo plutôt que le site officiel. La blacklist couvre 30+ domaines :

```python
DDG_BLACKLIST = {
    "linkedin.com", "pagesjaunes.fr", "societe.com", "manageo.fr",
    "pappers.fr", "verif.com", "kompass.com", "infogreffe.fr",
    "twitter.com", "facebook.com", "indeed.com", "welcometothejungle.com",
    "apec.fr", "glassdoor.fr", "cadremploi.fr",
    # + annuaires génériques : tout domaine contenant "annuaire"
}
```

---

## Extraction email

L'extraction cherche les emails dans deux endroits, par ordre de priorité :

1. **Balises `mailto:`** — les plus fiables, elles pointent directement vers une adresse utilisable
2. **Texte brut** (regex `[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}`) — capture les emails affichés en clair dans le HTML

Puis un filtre exclut les emails placeholder/techniques :
```python
EMAIL_EXCLUDE = re.compile(
    r"(noreply|no-reply|donotreply|support|info@example|test@|\.png|\.jpg|sentry|@schema)",
)
```

**Tri par priorité métier :** `recrutement` > `rh` > `contact` > `hello` > autres. L'email retenu est le premier de la liste triée — on préfère `recrutement@entreprise.fr` à `info@entreprise.fr`.

---

## Détection de page carrière

Deux stratégies enchaînées :

**Stratégie 1 — Liens dans le HTML de la page d'accueil**

Parcours de tous les `<a href>` de la homepage. Si le texte du lien ou l'URL contient un mot-clé carrière (`recrutement`, `careers`, `rejoindre`, `nous-rejoindre`, `offres emploi`...), on vérifie que le lien pointe vers le même domaine (évite les redirections vers LinkedIn Jobs).

**Stratégie 2 — Test de patterns d'URL**

Si aucun lien carrière n'est trouvé dans la nav, on teste directement des paths courants :
```
/recrutement  /carrieres  /careers  /jobs
/rejoindre    /emploi     /postuler /nous-rejoindre
```
Un 200 + présence d'au moins un mot-clé carrière dans le contenu valide la page (évite les "404 soft" qui retournent 200).

---

## Système de scoring A/B/C/D

Le score exprime la **facilité à envoyer une candidature spontanée** :

```
A — email direct (rh/recrutement/contact) + page carrière trouvée
    → candidature par email immédiate, page de référence disponible

B — page carrière trouvée, pas d'email direct
    → candidature via formulaire sur la page recrutement

C — email générique (info@) OU seulement formulaire de contact
    → candidature possible mais moins ciblée

D — rien trouvé
    → site inaccessible, sans formulaire ni email visible
```

**Seules les entreprises A et B passent en Phase 3.** Les C et D sont archivées dans `entreprises_rejetees.csv` pour audit.

---

## Reprise automatique et sauvegarde incrémentale

Le scraping de 600+ sites web prend 2-4h. Si le script est interrompu (réseau, rate-limit, coupure), il reprend automatiquement :

```python
mask_todo = df["statut"].isna() | (df["statut"] == "non_traité") | (df["statut"] == "url_introuvable")
todo = df[mask_todo].index.tolist()
```

Sauvegarde toutes les 10 entreprises dans `entreprises_enrichi.csv`. Rotation de session (nouveau User-Agent) toutes les 30 entreprises.

---

## Output

Fichier : `entreprises_enrichi.csv` — mêmes colonnes que Phase 1, plus :

| Colonne | Description |
|---|---|
| `url_resolue` | URL racine du site officiel |
| `email` | Email de contact (priorité rh/recrutement) |
| `page_carriere` | URL de la page recrutement si trouvée |
| `has_form` | `True` si formulaire de contact détecté |
| `score` | A / B / C / D |
| `statut` | `ok` / `url_introuvable` / `site_inaccessible` / `erreur: ...` |

---

## Usage

```bash
# Doit être lancé depuis la racine du projet (lit entreprises_brut.csv)
python phase2_enrichissement/enrichissement_phase2.py
# Durée : 2-4h selon la taille du CSV et les délais réseau
# Reprise automatique si interrompu (skip lignes déjà traitées)
```

→ Étape suivante : [`phase3_generation/`](../phase3_generation/README.md)

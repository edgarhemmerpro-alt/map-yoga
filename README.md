# Carte des profs — pipeline de données

Airtable (privé) → GitHub Actions (1×/jour) → `docs/profs.geojson` (public) → carte

Le token Airtable ne quitte jamais GitHub. Le navigateur ne voit que le GeoJSON,
qui ne contient ni email, ni téléphone, ni certificat.

## Mise en place (15 min)

### 1. Token Airtable
airtable.com/create/tokens → **Create new token**
- Scopes : `data.records:read` **et** `data.records:write` (le script réécrit lat/long)
- Access : **uniquement la base des profs**, pas « all workspaces »
- Copier le token (`pat...`), il n'est affiché qu'une fois

### 2. Base ID
Ouvrir la base → l'URL contient `airtable.com/appXXXXXXXXXXXXXX/...`
→ `appXXXXXXXXXXXXXX` est le Base ID.

### 3. Secrets GitHub
Repo → Settings → Secrets and variables → Actions → **New repository secret** :

| Nom | Valeur |
|---|---|
| `AIRTABLE_TOKEN` | `pat...` |
| `AIRTABLE_BASE_ID` | `app...` |
| `AIRTABLE_TABLE` | `Table 1` (le nom exact de ta table) |

### 4. Champs Airtable requis
`Latitude` et `Longitude` en type **Number**, précision 1.00000.

### 5. GitHub Pages
Settings → Pages → Source: **Deploy from a branch** → `main` / `/docs`
→ URL : `https://TONCOMPTE.github.io/TONREPO/`

### 6. Premier run
Actions → « Sync Airtable -> carte » → **Run workflow**.

## Garde-fous

- **Seuls les profs `Status = "Validé"` sortent.** 22 profs refusés et 7 en attente
  restent dans la base et n'atteignent jamais le GeoJSON. Statut vide ou inattendu
  = exclu par défaut.
- **Liste blanche de champs** (`CHAMPS_PUBLICS` dans `sync.py`). Ajouter un champ à
  la carte = ajouter une ligne ici, consciemment. `Mail`, `Numéro de téléphone` et
  `Diplôme` ne peuvent pas sortir.
- **Le script échoue si 0 prof est publié**, pour ne pas remplacer une carte qui
  marche par un fichier vide en cas de souci d'API.
- **Géocodage incrémental** : seules les lignes sans lat/long sont géocodées, et le
  résultat est mis en cache. Un nouveau prof = 1 appel, pas 96.

## Consommation

~30 appels API Airtable/mois (le plan gratuit en autorise ~1000).
Si la carte appelait Airtable depuis le navigateur : 1 appel par visiteur.

## Test à blanc

DRY_RUN=1 AIRTABLE_TOKEN=pat... AIRTABLE_BASE_ID=app... python scripts/sync.py
Génère le GeoJSON sans rien réécrire dans Airtable.

---

# La carte

`docs/index.html` — page autonome, à intégrer en iframe.

## Intégration Wix Studio

À transmettre au prestataire : ajouter un élément **Embed → Intégrer un site**
(Embed a site / iframe) et coller l'URL GitHub Pages.

- Hauteur conseillée : **700 px** (min. 520 px, sinon la carte est écrasée)
- Largeur : pleine largeur de section
- La page est responsive : sous 900 px, le panneau passe au-dessus de la carte

Rien d'autre à faire côté Wix. Pour changer le contenu de la carte, il ne touche
à rien : le workflow republie tout seul.

## Zéro requête tierce

Tout est servi depuis le repo : police (Poppins, 24 Ko), Leaflet, fond de carte
(Natural Earth), favicons. Une carte classique irait chercher ses tuiles chez
Mapbox ou Carto — l'IP de chaque visiteur partirait chez eux à chaque
chargement. Ici le navigateur ne contacte que ton domaine GitHub Pages.

Total : ~520 Ko, chargé une fois puis mis en cache.

Deux exceptions, toutes deux déclenchées par le visiteur lui-même :
- **« Ma position »** : API de géolocalisation du navigateur, avec demande de
  consentement. La position reste dans la page, aucun appel réseau.
- **Liens Site / Instagram** : ce sont des liens, le visiteur choisit de cliquer.

## Avatars

- Si le prof a un site → son favicon, téléchargé au build dans `docs/icons/`
- Sinon → ses initiales sur fond beige
- Si le favicon est cassé ou 404 → bascule automatique sur les initiales

Les favicons ne sont **pas** récupérés dans le navigateur : cela enverrait
l'IP du visiteur vers 34 sites tiers (ou chez Google) à chaque ouverture.

## Niveau de diplôme : volontairement absent

Le niveau (200h, 500h…) n'est ni affiché ni publié. Il ne figure pas dans
`profs.geojson` : un champ présent dans ce fichier est lisible par n'importe
qui, même si l'interface ne l'affiche pas. Le filtre porte donc sur le pays
uniquement.

Pour le réintroduire : décommenter `F_NIVEAU` dans `sync.py` et rajouter la
ligne dans `fiche()` (`index.html`).

## Chiffres

`+750 professeurs` et `65 pays` de la maquette sont fictifs. La page lit les
vrais chiffres dans `profs.geojson` (aujourd'hui : 66 profs, 13 pays) et se met
à jour toute seule. Rien à modifier à la main.

## Modifier l'apparence

Toutes les couleurs sont dans `:root` en haut de `index.html` :

    --creme    fond de page
    --panneau  fond de carte (océans)
    --terre    remplissage des pays
    --vert     pastilles de regroupement

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Airtable -> geocodage -> favicons -> docs/profs.geojson

Genere les donnees publiques de la carte. Le token Airtable reste cote
GitHub ; le GeoJSON produit ne contient ni email, ni telephone, ni diplome.
"""
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests

# ---------------------------------------------------------------- config

TOKEN = os.environ["AIRTABLE_TOKEN"]
BASE_ID = os.environ["AIRTABLE_BASE_ID"]
TABLE = os.environ.get("AIRTABLE_TABLE", "Table 1")

# >>> GARDE-FOU : seul ce statut est publie.
#     La table contient 22 profs refuses et 7 en attente : ils ne doivent
#     jamais atteindre la carte. Tout autre statut = exclu.
STATUT_PUBLIE = "Validé"

F_NOM, F_PRENOM = "Nom", "Prénom"
F_VILLE, F_PAYS = "Ville de pratique", "Pays de pratique"
F_LAT, F_LON = "Latitude", "Longitude"
F_STATUT = "Status"
# "Niveau de diplôme" est volontairement absent : non affiche sur la carte,
# donc non publie. Un champ present dans le GeoJSON est lisible par tous,
# meme si l'interface ne le montre pas.
F_SITE, F_INSTA = "Site internet", "Profil insta"

RACINE = Path(__file__).resolve().parent.parent
DOCS = RACINE / "docs"
SORTIE = DOCS / "profs.geojson"
CACHE_GEO = DOCS / ".geocache.json"
ICONES = DOCS / "icons"

API = f"https://api.airtable.com/v0/{BASE_ID}/{requests.utils.quote(TABLE)}"
HEAD = {"Authorization": f"Bearer {TOKEN}"}

# <<< A PERSONNALISER : Nominatim exige un contact reel et bloque les anonymes
UA = {"User-Agent": "carte-profs-yoga/1.0 (contact: edgarhemmerpro@gmail.com)"}

DRY_RUN = os.environ.get("DRY_RUN") == "1"
PAYS_BAN = {"France", "La Réunion", "Guyane française", "Martinique",
            "Guadeloupe", "Mayotte"}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# -------------------------------------------------- nettoyage des liens

RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
RE_DOMAINE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", re.I)


def url_site(v):
    """
    Normalise un site. Renvoie None si la valeur n'en est pas un.

    Le champ contient en pratique :
      - des domaines nus     : "www.yogamayucha.fr", "sandralarue.com"
      - des URL completes    : "https://loshakti.com/"
      - et au moins un EMAIL : "contac@aumness.fr"  <- ne doit JAMAIS sortir
    """
    if not v:
        return None
    v = str(v).strip().strip("<>\"' ")
    if not v:
        return None

    if RE_EMAIL.match(v) or ("@" in v and "//" not in v):
        log(f"  ! email detecte dans '{F_SITE}', ignore : {v}")
        return None

    if not v.startswith(("http://", "https://")):
        v = "https://" + v
    try:
        hote = (urlparse(v).hostname or "").strip()
    except ValueError:
        return None
    if not hote or not RE_DOMAINE.match(hote):
        log(f"  ! site illisible, ignore : {v}")
        return None
    return v


def url_insta(v):
    """
    Normalise vers https://instagram.com/<pseudo>.
    Le champ melange URLs a parametres de tracking (?igsh=...) et pseudos nus.
    """
    if not v:
        return None
    v = str(v).strip().strip("<>\"' ")
    if not v or RE_EMAIL.match(v):
        return None

    if "instagram.com" in v.lower():
        chemin = urlparse(v if "//" in v else "https://" + v).path
        pseudo = chemin.strip("/").split("/")[0]
    else:
        pseudo = v.lstrip("@").strip("/")

    pseudo = pseudo.split("?")[0].strip()
    if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", pseudo or ""):
        log(f"  ! insta illisible, ignore : {v}")
        return None
    return f"https://instagram.com/{pseudo}"


def nom_public(prenom, nom):
    """
    'Sarah' + 'Lambert' -> 'Sarah L.' (format de la maquette).

    Les prenoms sont saisis librement dans le formulaire Tally : on trouve
    'fanny', 'AUDREY', 'jean-marc'. On normalise la casse pour l'affichage
    public sans toucher a la base.
    """
    prenom, nom = (prenom or "").strip(), (nom or "").strip()
    if prenom:
        # capitalise chaque partie : 'jean-marc' -> 'Jean-Marc', 'AUDREY' -> 'Audrey'
        prenom = re.sub(r"[^\s\-']+",
                        lambda m: m.group(0)[:1].upper() + m.group(0)[1:].lower(),
                        prenom)
    if prenom and nom:
        return f"{prenom} {nom[0].upper()}."
    return prenom or (nom.title() if nom else "Professeur")


def initiales(prenom, nom):
    def p(s):
        s = unicodedata.normalize("NFD", (s or "").strip())
        return "".join(c for c in s if not unicodedata.combining(c))[:1].upper()
    return (p(prenom) + p(nom)) or "?"


# -------------------------------------------------------------- favicons

def favicon(site, rec_id):
    """
    Telecharge le favicon AU BUILD et le stocke dans le repo.

    Volontairement pas cote navigateur : cela enverrait l'IP de chaque
    visiteur vers 35 sites tiers (ou vers Google) a chaque chargement.
    """
    if not site:
        return None
    for f in ICONES.glob(f"{rec_id}.*"):
        return f"icons/{f.name}"  # deja en cache

    hote = urlparse(site).hostname
    candidats = []
    try:
        r = requests.get(site, headers=UA, timeout=10, allow_redirects=True)
        if r.ok:
            for m in re.finditer(
                    r'<link[^>]+rel=["\'][^"\']*icon[^"\']*["\'][^>]*>',
                    r.text[:200000], re.I):
                h = re.search(r'href=["\']([^"\']+)["\']', m.group(0), re.I)
                if h:
                    candidats.append(requests.compat.urljoin(r.url, h.group(1)))
    except Exception:
        pass
    candidats.append(f"https://{hote}/favicon.ico")

    for u in candidats:
        try:
            r = requests.get(u, headers=UA, timeout=10)
            ct = r.headers.get("content-type", "").lower()
            if r.ok and len(r.content) > 70 and "image" in ct:
                sous = ct.split("/")[-1].split(";")[0].strip()
                ext = {"png": "png", "svg+xml": "svg", "jpeg": "jpg",
                       "jpg": "jpg", "gif": "gif"}.get(sous, "ico")
                ICONES.mkdir(parents=True, exist_ok=True)
                (ICONES / f"{rec_id}.{ext}").write_bytes(r.content)
                return f"icons/{rec_id}.{ext}"
        except Exception:
            continue
    log(f"  . pas de favicon pour {hote} -> initiales")
    return None


# -------------------------------------------------------------- airtable

def lire_records():
    out, offset = [], None
    while True:
        p = {"pageSize": 100}
        if offset:
            p["offset"] = offset
        r = requests.get(API, headers=HEAD, params=p, timeout=30)
        r.raise_for_status()
        d = r.json()
        out += d["records"]
        offset = d.get("offset")
        if not offset:
            return out
        time.sleep(0.25)  # Airtable : 5 req/s max par base


def ecrire_coords(maj):
    if not maj:
        return
    if DRY_RUN:
        log(f"[dry-run] {len(maj)} lignes auraient ete mises a jour")
        return
    for i in range(0, len(maj), 10):
        r = requests.patch(API, headers={**HEAD, "Content-Type": "application/json"},
                           json={"records": maj[i:i + 10]}, timeout=30)
        r.raise_for_status()
        time.sleep(0.25)
    log(f"{len(maj)} lignes mises a jour dans Airtable")


# ------------------------------------------------------------- geocodage

def geocode_ban(ville, pays):
    q = urlencode({"q": ville, "type": "municipality", "limit": 1})
    r = requests.get(f"https://api-adresse.data.gouv.fr/search/?{q}",
                     headers=UA, timeout=15)
    r.raise_for_status()
    f = r.json().get("features") or []
    if not f:
        return None
    lon, lat = f[0]["geometry"]["coordinates"]
    return lat, lon


def geocode_nominatim(ville, pays):
    q = urlencode({"q": f"{ville}, {pays}", "format": "json", "limit": 1})
    r = requests.get(f"https://nominatim.openstreetmap.org/search?{q}",
                     headers=UA, timeout=15)
    r.raise_for_status()
    d = r.json()
    time.sleep(1.1)  # politesse Nominatim : ne pas retirer
    return (float(d[0]["lat"]), float(d[0]["lon"])) if d else None


def geocode(ville, pays, cache):
    cle = f"{ville}|{pays}"
    if cle in cache:
        return cache[cle]
    for fn in ([geocode_ban, geocode_nominatim] if pays in PAYS_BAN
               else [geocode_nominatim]):
        try:
            res = fn(ville, pays)
        except Exception as e:
            log(f"  ! {fn.__name__} a echoue sur {cle} : {e}")
            continue
        if res:
            cache[cle] = [round(res[0], 5), round(res[1], 5)]
            return cache[cle]
    log(f"  ! ECHEC geocodage : {cle}")
    return None


# ------------------------------------------------------------------ main

def main():
    records = lire_records()
    log(f"{len(records)} records lus")

    cache = json.loads(CACHE_GEO.read_text()) if CACHE_GEO.exists() else {}
    maj, feats = [], []
    st = {"publies": 0, "exclus": 0, "geocodes": 0, "sans_coord": 0, "favicons": 0}

    for rec in records:
        f = rec.get("fields", {})

        if (f.get(F_STATUT) or "").strip() != STATUT_PUBLIE:
            st["exclus"] += 1
            continue

        ville = (f.get(F_VILLE) or "").strip()
        pays = (f.get(F_PAYS) or "").strip()
        lat, lon = f.get(F_LAT), f.get(F_LON)

        if (lat is None or lon is None) and ville and pays:
            log(f"  geocodage : {ville}, {pays}")
            res = geocode(ville, pays, cache)
            if res:
                lat, lon = res
                maj.append({"id": rec["id"], "fields": {F_LAT: lat, F_LON: lon}})
                st["geocodes"] += 1

        if lat is None or lon is None:
            st["sans_coord"] += 1
            continue

        site = url_site(f.get(F_SITE))
        insta = url_insta(f.get(F_INSTA))

        ico = favicon(site, rec["id"]) if site else None
        if ico:
            st["favicons"] += 1

        props = {"nom": nom_public(f.get(F_PRENOM), f.get(F_NOM)),
                 "ini": initiales(f.get(F_PRENOM), f.get(F_NOM)),
                 "ville": ville, "pays": pays}
        if site:
            props["site"] = site
        if insta:
            props["insta"] = insta
        if ico:
            props["ico"] = ico

        # ceinture et bretelles : rien de sensible ne doit sortir
        blob = json.dumps(props, ensure_ascii=False)
        assert "@" not in blob, f"@ dans la sortie publique : {blob}"
        assert not re.search(r"\+?\d[\d ().-]{8,}", blob), \
            f"telephone dans la sortie publique : {blob}"

        feats.append({"type": "Feature",
                      "geometry": {"type": "Point",
                                   "coordinates": [float(lon), float(lat)]},
                      "properties": props})
        st["publies"] += 1

    ecrire_coords(maj)
    CACHE_GEO.write_text(json.dumps(cache, ensure_ascii=False, indent=0))

    nb_pays = len({x["properties"]["pays"] for x in feats})
    DOCS.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(json.dumps({
        "type": "FeatureCollection",
        "maj": time.strftime("%Y-%m-%d"),
        "stats": {"profs": st["publies"], "pays": nb_pays},
        "features": feats,
    }, ensure_ascii=False, indent=1))

    log(json.dumps(st, indent=2))
    if st["publies"] == 0:
        log("ERREUR : 0 prof publie -> on ne remplace pas la carte par du vide")
        sys.exit(1)
    log(f"-> {SORTIE} : {st['publies']} profs, {nb_pays} pays")


if __name__ == "__main__":
    main()

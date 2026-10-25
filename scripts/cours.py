#!/usr/bin/env python3
"""Récupère les cours des positions suivies et écrit cours.json.

Usage : python3 scripts/cours.py

Tourne dans GitHub Actions, une fois par jour après la clôture d'Euronext. Ne lit
que `tickers.json` — la liste des symboles, sans aucune quantité — et n'écrit que
`cours.json`. Les deux sont publics : un cours de bourse n'apprend rien sur le
portefeuille de qui le consulte.

Les cryptos passent par **CoinGecko**, qui accepte les appels navigateur : la page
les rafraîchit elle-même à chaque ouverture et ne se sert de cours.json que de repli.

Les ETF Euronext sont le point dur. Aucune source gratuite ne cote WPEA et PAASI de
façon garantie, et aucune ne renvoie d'en-tête CORS — d'où ce script côté serveur,
et d'où la chaîne de sources ci-dessous, essayées dans l'ordre :

1. **Twelve Data**, si la variable d'environnement `TWELVEDATA_KEY` existe (secret
   du dépôt). C'est la voie fiable : compte gratuit, 800 appels par jour, largement
   de quoi relever deux symboles une fois par jour.
2. **Yahoo Finance**, sans clé ni compte. Marche souvent, mais répond 429 dès qu'une
   adresse IP est jugée trop bavarde — ce qui arrive sur les serveurs partagés de
   GitHub Actions. D'où le passage par cookie + crumb et les deux tentatives.
3. Le cours précédent de cours.json, conservé et marqué `perime`.

Un cours d'hier annoncé comme tel vaut mieux qu'une page vide : la page affiche la
fraîcheur du relevé, et retombe sur la valeur du classeur si tout échoue.
"""
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
# Import direct de la classe : le module `http` serait masqué par la fonction `http`
# définie plus bas.
from http.cookiejar import CookieJar

RACINE = pathlib.Path(__file__).resolve().parent.parent
TICKERS = RACINE / "tickers.json"
SORTIE = RACINE / "cours.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
YAHOO = "https://query{}.finance.yahoo.com/v8/finance/chart/{}?interval=1d&range=5d"
COINGECKO = ("https://api.coingecko.com/api/v3/simple/price"
             "?ids={}&vs_currencies=eur&include_24hr_change=true")
TWELVE = "https://api.twelvedata.com/quote?symbol={}&mic_code=XPAR&apikey={}"


def http(url, timeout=25, opener=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    ouvre = opener.open if opener else urllib.request.urlopen
    with ouvre(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def twelvedata(symboles, cle):
    """Source principale quand la clé est configurée. Un symbole par appel."""
    out, erreurs = {}, {}
    for s in symboles:
        base = s.split(".")[0]                      # « WPEA.PA » → « WPEA »
        try:
            d = http(TWELVE.format(urllib.parse.quote(base), urllib.parse.quote(cle)))
            if d.get("status") == "error" or "close" not in d:
                raise ValueError(d.get("message", "réponse inattendue"))
            out[s] = {
                "prix": round(float(d["close"]), 4),
                "devise": d.get("currency", "EUR"),
                "variation": round(float(d.get("percent_change") or 0), 3),
                "nom": d.get("name"),
                "source": "twelvedata",
            }
        except Exception as e:
            erreurs[s] = f"twelvedata {type(e).__name__}: {e}"
        time.sleep(8.5)                             # 8 appels/minute en offre gratuite
    return out, erreurs


def _opener_yahoo():
    """Yahoo exige un cookie de consentement avant de délivrer un crumb."""
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    op.addheaders = [("User-Agent", UA), ("Accept", "*/*")]
    try:
        op.open("https://fc.yahoo.com", timeout=15).read()
    except Exception:
        pass                                        # 404 attendu : seul le cookie compte
    return op


def yahoo(symboles):
    """Repli sans clé. Deux hôtes, deux tentatives, un cookie — Yahoo 429 facilement."""
    out, erreurs = {}, {}
    op = _opener_yahoo()
    for s in symboles:
        dernier = None
        for tentative, hote in enumerate((1, 2, 1)):
            try:
                meta = http(YAHOO.format(hote, urllib.parse.quote(s)),
                            opener=op)["chart"]["result"][0]["meta"]
                prix = meta.get("regularMarketPrice")
                if prix is None:
                    raise ValueError("pas de regularMarketPrice")
                out[s] = {
                    "prix": round(float(prix), 4),
                    "devise": meta.get("currency", "EUR"),
                    "variation": round(float(meta.get("regularMarketChangePercent") or 0), 3),
                    "cloture_precedente": meta.get("chartPreviousClose"),
                    "nom": meta.get("longName") or meta.get("shortName"),
                    "horodatage": meta.get("regularMarketTime"),
                    "source": "yahoo",
                }
                break
            except Exception as e:
                dernier = f"yahoo {type(e).__name__}: {e}"
                time.sleep(3 * (tentative + 1))
        if s not in out:
            erreurs[s] = dernier
    return out, erreurs


def etf(symboles):
    """Twelve Data si la clé existe, Yahoo pour le reste."""
    if not symboles:
        return {}, {}
    cle = os.environ.get("TWELVEDATA_KEY", "").strip()
    out, erreurs = ({}, {})
    if cle:
        out, erreurs = twelvedata(symboles, cle)
    restants = [s for s in symboles if s not in out]
    if restants:
        o2, e2 = yahoo(restants)
        out.update(o2)
        for s, msg in e2.items():
            erreurs[s] = (erreurs.get(s, "") + " | " + msg).strip(" |")
        for s in o2:
            erreurs.pop(s, None)
    return out, erreurs


def coingecko(ids):
    """Un seul appel pour toutes les cryptos — l'API accepte une liste."""
    if not ids:
        return {}, {}
    try:
        brut = http(COINGECKO.format(",".join(ids)))
    except Exception as e:
        return {}, {"*": f"{type(e).__name__}: {e}"}
    out, erreurs = {}, {}
    for i in ids:
        if i in brut and "eur" in brut[i]:
            out[i] = {"prix": brut[i]["eur"],
                      "devise": "EUR",
                      "variation": round(float(brut[i].get("eur_24h_change") or 0), 3)}
        else:
            erreurs[i] = "absent de la réponse"
    return out, erreurs


def main():
    if not TICKERS.exists():
        sys.exit("tickers.json absent — lancer scripts/build.py d'abord.")
    tk = json.loads(TICKERS.read_text(encoding="utf-8"))

    precedent = {}
    if SORTIE.exists():
        try:
            precedent = json.loads(SORTIE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass                                    # fichier corrompu : on repart à neuf

    y, ey = etf(tk.get("yahoo", []))
    c, ec = coingecko(tk.get("coingecko", []))

    # Reprendre l'ancien cours pour tout ce qui a échoué, en le marquant.
    for cle, frais, rates in (("yahoo", y, ey), ("coingecko", c, ec)):
        for s in (tk.get(cle) or []):
            if s in frais:
                continue
            vieux = (precedent.get(cle) or {}).get(s)
            if vieux:
                frais[s] = dict(vieux, perime=True,
                                erreur=rates.get(s) or rates.get("*"))

    data = {
        "maj": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "yahoo": y,
        "coingecko": c,
        "erreurs": {k: v for k, v in list(ey.items()) + list(ec.items())},
    }
    SORTIE.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")

    lignes = [f"{s} {v['prix']} {v['devise']}" + (" (périmé)" if v.get("perime") else "")
              for d in (y, c) for s, v in d.items()]
    print("✅ cours.json — " + " · ".join(lignes))
    if data["erreurs"]:
        # Sortie 0 quand même : le workflow doit committer les cours qui ont marché.
        print("⚠️  " + " · ".join(f"{k} : {v}" for k, v in data["erreurs"].items()))


if __name__ == "__main__":
    main()

# patrimoine

Page de suivi de patrimoine personnel, publiée sur GitHub Pages.

**Ce dépôt est public et ne contient aucune donnée.** Pas de chiffres, pas de noms,
pas même un fichier chiffré : seulement du code. Les données vivent dans un dépôt
privé, que la page lit à l'ouverture avec un jeton de lecture seule collé par
l'utilisatrice.

```
index.html              Toute la page : mise en page, graphiques, connexion
cours.json              Cours du jour (public — un cours n'apprend rien sur personne)
tickers.json            Symboles à relever (public — aucune quantité)
scripts/cours.py        Relève les cours → cours.json
.github/workflows/      Relevé quotidien
```

Pas de build, pas de dépendances, pas de framework : `index.html` est édité
directement et servi tel quel.

## Le modèle de sécurité

```
   Dépôt PRIVÉ (données)                 Dépôt PUBLIC (ce dépôt)
   data/patrimoine.json                  index.html + cours.json
   data/portefeuille.json                         │
            ▲                                     │ GitHub Pages sert ces fichiers
            │  API GitHub « contents »            ▼
            └──── jeton lecture seule ──────  NAVIGATEUR
                                              lit → calcule → dessine
```

Rien de sensible n'est jamais publié. Qui tombe sur l'adresse voit un écran de
connexion et une page vide.

Le jeton est **fine-grained**, limité au seul dépôt de données, permission
**Contents : Read-only**, durée **90 jours**. S'il fuite, il se révoque d'un clic
et n'aura jamais donné que la lecture de ce dépôt. C'est la différence avec un
fichier chiffré publié : là, rien n'est dehors, et tout est révocable.

La page impose aussi une CSP qui ne l'autorise à parler qu'à trois adresses :
elle-même, `api.github.com` et `api.coingecko.com`. Aucun script tiers n'est chargé.

## Mise en service

1. **Créer le jeton** sur
   [github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new) :
   *Repository access* → *Only select repositories* → le dépôt de données ;
   *Permissions* → *Repository permissions* → **Contents : Read-only** ;
   expiration 90 jours. Rien d'autre.

2. **Activer Pages** : Settings → Pages → *Deploy from a branch* → `main` / `/ (root)`.

3. **Autoriser le workflow à écrire** : Settings → Actions → General →
   *Workflow permissions* → **Read and write**. Sans ça le relevé des cours ne peut
   pas se committer.

4. Ouvrir la page, coller le jeton, cocher « se souvenir » si c'est ton ordinateur.

## Au quotidien

Ce dépôt ne bouge que si l'interface change. Les chiffres se mettent à jour dans le
dépôt de données — la page les relit à la prochaine ouverture, sans rien republier
ici.

Tous les 90 jours le jeton expire : la page le dit, on en régénère un et on le
recolle.

## Les cours

**Cryptos** — CoinGecko, appelée directement par la page à chaque ouverture : les
montants crypto sont ceux de l'instant.

**ETF** — Yahoo Finance ne renvoie pas d'en-tête CORS, donc la page ne peut pas
l'appeler. Un workflow relève les symboles de `tickers.json` chaque soir de semaine
après la clôture d'Euronext et dépose le résultat dans `cours.json`.

⚠️ **Yahoo répond 429 dès qu'une adresse IP lui paraît trop bavarde**, et les
serveurs d'Actions sont partagés. Si l'onglet Actions montre des échecs répétés :
créer un compte gratuit sur [twelvedata.com](https://twelvedata.com), puis
Settings → Secrets and variables → Actions → New repository secret, nom
`TWELVEDATA_KEY`. `cours.py` l'utilisera en priorité et Yahoo ne servira plus que de
repli. 800 appels par jour en offre gratuite, pour deux symboles quotidiens.

Si tout échoue, le cours précédent est conservé et la page affiche la date du
relevé. Elle ne montre jamais un chiffre périmé sans le dire : le badge passe à
« ETF non relevés » au-delà de quatre jours.

Les workflows programmés sont suspendus par GitHub après 60 jours sans activité sur
le dépôt. Un push occasionnel suffit à les garder actifs.

## Ajouter une position

Les quantités vivent dans le dépôt de données. Si une nouvelle ligne apparaît, il
faut aussi ajouter son symbole ici, dans `tickers.json`, sinon le relevé quotidien
ne la cherchera pas. La page le signale : la position s'affiche sans cours et le
total est marqué incomplet.

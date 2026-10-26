# Veille PNC ✈️

Ce dépôt surveille automatiquement les offres d'emploi **PNC** (hôtesse de l'air, steward, personnel navigant
commercial) des compagnies aériennes basées en France et en outre-mer. Il vous prévient **en moins de 20 minutes**
sur votre téléphone (ntfy), sur Discord et/ou par e-mail, **à chaque nouvelle offre PNC publiée**.

- Tout tourne gratuitement sur **GitHub Actions** : pas de serveur, rien à installer sur votre ordinateur.
- Toutes les 15 minutes, la veille relit les sites des compagnies, repère les nouvelles offres, garde celles qui
  concernent un poste PNC et vous les envoie, sans exception.
- Elle vous prévient aussi si un site change au point de ne plus pouvoir être lu (« source en panne »).

> 🔒 Le dépôt est **public**. Vos informations personnelles (adresses, jetons) ne vont **jamais** dans les
> fichiers du dépôt : elles se rangent dans les **secrets** GitHub, invisibles pour les visiteurs.

---

## Sommaire

1. [Autoriser le workflow à enregistrer son état](#1-autoriser-le-workflow-à-enregistrer-son-état)
2. [Créer vos canaux de notification](#2-créer-vos-canaux-de-notification)
3. [Ajouter les secrets dans GitHub](#3-ajouter-les-secrets-dans-github)
4. [Lancer le premier run à la main](#4-lancer-le-premier-run-à-la-main)
5. [Lire le résumé d'un run](#5-lire-le-résumé-dun-run)
6. [Comprendre les notifications](#6-comprendre-les-notifications)
7. [Vérifier que tout marche](#7-vérifier-que-tout-marche)
8. [Sources surveillées](#8-sources-surveillées)
9. [Dépannage](#9-dépannage)
10. [Pour les développeurs](#10-pour-les-développeurs)

---

## 1. Autoriser le workflow à enregistrer son état

La veille garde la liste des offres déjà vues dans le fichier `data/state.json` et l'enregistre (« commit ») après
chaque run. Il faut l'y autoriser une fois :

1. Sur la page du dépôt, cliquez sur **Settings** (⚙️, en haut à droite).
2. Menu de gauche : **Actions** → **General**.
3. Tout en bas, section **Workflow permissions** : cochez **Read and write permissions**, puis **Save**.
4. Toujours dans **Actions** → **General**, en haut, vérifiez que **Allow all actions and reusable workflows** est coché.

---

## 2. Créer vos canaux de notification

Chaque canal est **facultatif** : n'activez que ceux qui vous servent (au moins un, sinon vous ne recevrez rien).
Gardez les valeurs obtenues dans un coin : vous les collerez dans GitHub à l'étape 3.

### 📱 ntfy (notifications sur le téléphone) — recommandé

ntfy est une application gratuite qui affiche une notification dès qu'un message arrive sur un « sujet » (topic).

1. Installez l'application **ntfy** ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
   ou [iPhone](https://apps.apple.com/app/ntfy/id1625396347)).
2. Inventez un nom de sujet **long et impossible à deviner** : un sujet ntfy est public, quiconque connaît son nom
   peut lire vos messages. Par exemple `veille-pnc-` suivi de 20 lettres et chiffres au hasard
   (utilisez un générateur de mots de passe, **sans** caractères spéciaux), ex. `veille-pnc-k8f2m9xq4tz7wr1bn5hd`.
3. Dans l'application : **+** → **Subscribe to topic** → collez ce nom → **Subscribe**.
4. Valeur à garder : le nom du sujet → secret `NTFY_TOPIC`.

Les nouvelles offres PNC arrivent en priorité haute (son + bannière), avec un bouton **Voir l'offre**.

### 💬 Discord

1. Dans votre serveur Discord (créez-en un gratuitement si besoin : **+** dans la barre de gauche), faites un clic
   droit sur le salon qui recevra les offres → **Modifier le salon**.
2. **Intégrations** → **Webhooks** → **Nouveau webhook** → donnez-lui un nom (« Veille PNC »).
3. **Copier l'URL du webhook**. Valeur à garder → secret `DISCORD_WEBHOOK_URL`.

### 📧 E-mail (Gmail)

Gmail exige un **mot de passe d'application** (pas votre mot de passe habituel) :

1. Activez la **validation en deux étapes** sur votre compte Google : <https://myaccount.google.com/security>.
2. Ouvrez <https://myaccount.google.com/apppasswords>, saisissez un nom (« Veille PNC ») → **Créer**.
3. Google affiche un mot de passe de 16 lettres : copiez-le **sans les espaces** → secret `SMTP_PASSWORD`.
4. Autres valeurs : `SMTP_HOST` = `smtp.gmail.com`, `SMTP_PORT` = `465`, `SMTP_USER` = votre adresse Gmail,
   `EMAIL_TO` = l'adresse qui recevra les alertes (peut être la même).

Si plusieurs offres arrivent pendant le même run, vous recevez **un seul e-mail récapitulatif**.

---

## 3. Ajouter les secrets dans GitHub

1. **Settings** → menu de gauche **Secrets and variables** → **Actions**.
2. Pour chaque ligne du tableau ci-dessous que vous utilisez : **New repository secret**, tapez le **nom exact**
   (en majuscules) dans *Name*, collez la valeur dans *Secret*, puis **Add secret**.

| Canal | Nom du secret | Valeur |
|---|---|---|
| ntfy | `NTFY_TOPIC` | le nom de votre sujet |
| ntfy | `NTFY_SERVER` | facultatif, `https://ntfy.sh` par défaut |
| Discord | `DISCORD_WEBHOOK_URL` | l'URL du webhook |
| E-mail | `SMTP_HOST` | `smtp.gmail.com` |
| E-mail | `SMTP_PORT` | `465` |
| E-mail | `SMTP_USER` | votre adresse Gmail |
| E-mail | `SMTP_PASSWORD` | le mot de passe d'application (16 lettres) |
| E-mail | `EMAIL_TO` | l'adresse qui reçoit les alertes |
| Alerte Google | `GOOGLE_ALERT_FRENCHBEE` | adresse du flux de l'alerte French Bee (section 8) |
| Alerte Google | `GOOGLE_ALERT_AIRAUSTRAL` | adresse du flux de l'alerte Air Austral (section 8) |

Un canal n'est activé que si **tous** ses secrets sont présents. Si un canal tombe en panne, les autres continuent.

---

## 4. Lancer le premier run à la main

1. Onglet **Actions** du dépôt. Si GitHub affiche un bouton vert « I understand my workflows, go ahead and enable
   them », cliquez dessus.
2. À gauche, cliquez sur **Veille PNC**, puis à droite sur **Run workflow** → **Run workflow** (bouton vert).
   - *Facultatif* : cochez d'abord **Essai à blanc** pour un premier test sans rien envoyer ni enregistrer.
3. Attendez 1 à 2 minutes (rafraîchissez la page) : le run passe au vert ✅.

Le **premier vrai run est silencieux** : la veille enregistre toutes les offres déjà en ligne sans vous les envoyer
une par une, puis vous envoie **un seul message** « ✅ Veille PNC active – N offres indexées, dont X PNC » avec la
liste des offres PNC déjà en ligne. C'est la confirmation que vos canaux fonctionnent.

Ensuite la veille tourne **toute seule toutes les 15 minutes** (à h07, h22, h37, h52). Vous n'avez plus rien à faire.

> ℹ️ GitHub peut retarder les runs programmés de quelques minutes aux heures chargées : c'est normal.

---

## 5. Lire le résumé d'un run

**Actions** → cliquez sur un run → le **résumé** s'affiche sous le schéma du job :

| Colonne | Signification |
|---|---|
| Source | identifiant de la source (voir section 8) |
| Statut | `ok`, `ok (changement)` pour une page surveillée qui a changé, `❌ …` en cas d'échec, `⏸ en pause` si le site refuse l'accès |
| Offres | nombre d'offres actuellement en ligne sur cette source (`page` pour une page surveillée) |
| Nouvelles | offres apparues depuis le run précédent |

En dessous : les offres PNC notifiées, l'état de chaque canal (✅ / ❌ avec la raison) et d'éventuelles **notes**
(nettoyage de l'état, canaux en échec…).

Un commit « chore(état): mise à jour de la veille » apparaît dans l'historique quand l'état change : c'est normal,
c'est la mémoire de la veille (et ces commits empêchent GitHub de désactiver le workflow après 60 jours).

---

## 6. Comprendre les notifications

**Chaque nouvelle offre PNC vous est envoyée**, quelle que soit la base ou le contrat. Une notification d'offre
contient : la compagnie, l'intitulé, le lieu, le contrat, la date de publication (quand le site les donne) et un
bouton **Voir l'offre**.

| Message | Quand |
|---|---|
| ✈️ *Nouvelle offre PNC – Compagnie* | Une offre PNC vient d'être publiée (au-delà de 5 offres dans le même run : un seul message qui les liste toutes) |
| 📣 *Compagnie : la page recrutement PNC a changé* | Une page « campagne » surveillée a changé, avec un extrait du nouveau texte |
| ⚠️ *Source en panne* | Une source échoue 3 fois de suite (une seule alerte, pas de spam) |
| ✅ *Source rétablie* | La source fonctionne de nouveau |
| 📊 *Résumé de la semaine* | Le lundi matin : offres vues par source et état des sources (preuve que la veille tourne) |

Selon le canal :
- **ntfy** : une notification par offre, titre « Compagnie — Intitulé », lieu / contrat / date en dessous.
- **Discord** : une carte par offre (titre cliquable, lieu, contrat et date en colonnes).
- **E-mail** : **un seul e-mail par run**, avec une carte et un bouton par offre.

**Détection PNC** : l'intitulé (ou, à défaut, la description) doit contenir un terme comme *PNC*, *hôtesse de
l'air*, *steward*, *cabin crew*, *chef de cabine*… et l'intitulé ne doit pas contenir de terme d'exclusion
(*pilote*, *mécanicien cabine*, *planning PN*, *stage*, *directeur*, *hôtesse d'accueil*…). Les postes
d'*instructeur PNC* sont aussi envoyés, avec la mention « Instructeur PNC ».

---

## 7. Vérifier que tout marche

- **Test d'une notification** : ouvrez `data/state.json` dans GitHub (crayon ✏️), supprimez une entrée d'offre PNC
  (le bloc entre accolades qui commence par `"airfrance_pn::…"` par exemple, virgule comprise), validez
  (*Commit changes*), puis relancez le workflow à la main : l'offre est vue comme nouvelle et vous est envoyée sur
  chaque canal. *(S'il n'y a aucune offre PNC en ligne, supprimez n'importe quelle offre : elle sera réindexée sans
  notification, ce qui prouve au moins que la détection fonctionne.)*
- **Test d'une source en panne** : dans `config/sources.yaml`, remplacez l'URL d'une source par une adresse
  invalide. Après 3 runs, vous recevez une alerte « ⚠️ Source en panne », une seule fois. Remettez l'URL : vous
  recevez « ✅ Source rétablie ».

---

## 8. Sources surveillées

La liste complète et les réglages sont dans [`config/sources.yaml`](config/sources.yaml) (vérifiés le 26/10/2026).

| id | Compagnie | Méthode |
|---|---|---|
| `airfrance_pnc` | Air France | flux RSS du profil « Personnel Navigant Commercial » |
| `airfrance_pn` | Air France | flux RSS de la famille « Personnel Navigant » (filet de sécurité) |
| `hop` | Groupe Air France, dont HOP! | flux RSS des 20 dernières offres du groupe (le filtre HOP! est ignoré par le site) |
| `aircalin` | Aircalin | flux RSS famille PNC |
| `easyjet` | easyJet | flux RSS (~10 dernières offres), offres en France uniquement |
| `transavia` | Transavia France | API publique du site carrières (DigitalRecruiters) |
| `airtahitinui` | Air Tahiti Nui | page liste (HTML) |
| `asl` | ASL Airlines France | page liste (HTML), offres en France uniquement |
| `aircaraibes` | Air Caraïbes | sitemap + lecture des nouvelles pages offres dans un navigateur |
| `frenchbee_ats` | French Bee | sitemap + lecture des nouvelles pages offres |
| `aircorsica` | Air Corsica | liste rendue dans un navigateur |
| `frenchbee_alerte` | French Bee | alerte Google `"French Bee" PNC recrutement` |
| `airaustral_alerte` | Air Austral | alerte Google `"Air Austral" recrutement PNC` |

### Alertes Google (French Bee, Air Austral)

Les sites de French Bee (`www.frenchbee.com`) et d'Air Austral bloquent les programmes automatiques ; la veille
respecte ces protections. Les sources `frenchbee_pnc` et `airaustral` sont donc désactivées et remplacées par des
**alertes Google** : Google, lui, explore ces sites et la presse. Quand une page ou un article correspondant à la
recherche apparaît, l'alerte le publie dans un flux que la veille lit toutes les 15 minutes. Comptez **quelques
heures** de délai entre la publication et l'arrivée dans Google. Chaque entrée vous est envoyée avec la mention
🔎 *Alerte Google* et un bouton **Lire l'article** : c'est un article ou une page web, pas forcément une offre.

Créer une alerte (ou en ajouter pour une autre compagnie, ex. Corsair) :
1. Ouvrez <https://www.google.com/alerts>, tapez la recherche (ex. `"French Bee" PNC recrutement`).
2. **Afficher les options** → *Fréquence* : « Au fil de l'eau » ; *Distribuer à* : **Flux RSS** → **Créer**.
3. Cliquez sur l'icône RSS de l'alerte et copiez l'adresse de la page
   (`https://www.google.com/alerts/feeds/…`).
4. Collez-la dans le secret correspondant (`GOOGLE_ALERT_FRENCHBEE`, `GOOGLE_ALERT_AIRAUSTRAL`). L'adresse contient
   l'identifiant de votre compte Google : elle ne doit pas être écrite dans le dépôt public.

Pour une nouvelle alerte, il faut aussi un bloc dans `config/sources.yaml` (type `rss`, `url_env: NOM_DU_SECRET`,
`notify_all: true`) et une ligne `NOM_DU_SECRET: ${{ secrets.NOM_DU_SECRET }}` dans `.github/workflows/veille.yml`.

### Ajouter une compagnie

Ajoutez un bloc dans `config/sources.yaml` : pas de code à écrire si le site utilise un type déjà pris en charge.

| type | Pour quoi | Réglages principaux |
|---|---|---|
| `rss` | flux RSS ou Atom (Talentsoft, Taleo, alertes Google…) | `url` |
| `digitalrecruiters` | sites carrières DigitalRecruiters / Cegid | `domain` |
| `html_list` | liste d'offres dans le HTML de la page | `url`, `item`, `title`, `link`, `fields`, `empty_text` (sélecteurs CSS) |
| `browser` | liste d'offres affichée par JavaScript | comme `html_list` + `wait_for` |
| `sitemap` | sites dont le sitemap liste les offres (Hellowork…) | `url`, `url_pattern` |
| `page_watch` | page « campagne » sans liste d'offres | `url`, `zone`, `exclude`, `ignore_lines` |

Options communes : `enabled: false` pour couper une source, `keep_if_any: [mots]` pour ne garder que les offres
dont l'intitulé ou le lieu contient un de ces mots, `notify_all: true` pour envoyer chaque nouvelle entrée sans
détection PNC, `url_env: SECRET` pour lire l'URL dans un secret. Une source ajoutée plus tard est initialisée silencieusement,
comme au premier lancement.

---

## 9. Dépannage

| Problème | Solution |
|---|---|
| Aucun message reçu | Vérifiez dans le résumé du run la ligne **Canaux** : un ❌ indique la raison. Vérifiez le nom exact des secrets. |
| E-mail : « authentification SMTP refusée » | Utilisez un **mot de passe d'application** Gmail, collé sans espaces. |
| Le run échoue à l'étape « Enregistrer l'état » | Revoyez l'étape 1 (*Read and write permissions*). |
| Une source est « ❌ » | Si c'est passager, rien à faire. Après 3 échecs vous recevez une alerte : le site a sans doute changé et `config/sources.yaml` doit être adapté. |
| Le workflow ne tourne plus | GitHub coupe les workflows programmés après 60 jours sans activité : onglet **Actions** → **Veille PNC** → **Enable workflow**. Normalement les commits d'état l'évitent. |
| Je veux repartir de zéro | Remplacez le contenu de `data/state.json` par `{}` : le run suivant refait une initialisation silencieuse. |

---

## 10. Pour les développeurs

```bash
python -m venv .venv && .venv/Scripts/activate          # Windows (Linux/macOS : source .venv/bin/activate)
pip install -r requirements-dev.txt -r requirements-browser.txt
python -m playwright install chromium

export PYTHONPATH=src                                    # PowerShell : $env:PYTHONPATH="src"
python -m pytest -q                                      # tests (fixtures enregistrées, sans réseau)
python -m veille --dry-run                               # tout tester : aucune notification, état non modifié
python -m veille --dry-run --source transavia            # une seule source (même désactivée)
python -m veille --weekly --dry-run                      # aperçu du résumé hebdomadaire
```

Architecture : `src/veille/main.py` orchestre *relève → diff → filtre PNC → notifie → sauvegarde* ;
`sources/` contient un module par **type** de source, `matching.py` la détection PNC, `messages.py` le contenu des messages, `state.py` l'état,
`notifiers/` les canaux. Politesse : User-Agent explicite, délai de 20 s, 2 tentatives maximum, une requête à la
fois par domaine ; un site qui répond 403/429 est mis en pause 6 h après 3 refus, sans insister.

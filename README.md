# Veille PNC ✈️

Ce dépôt surveille automatiquement les offres d'emploi **PNC** (hôtesse de l'air, steward, personnel navigant
commercial) des compagnies aériennes basées en France et en outre-mer. Il vous prévient **en moins de 20 minutes**
sur votre téléphone, Discord, Telegram et/ou par e-mail, avec un score qui indique si l'offre correspond à votre profil.

- Tout tourne gratuitement sur **GitHub Actions** : pas de serveur, rien à installer sur votre ordinateur.
- Toutes les 15 minutes, la veille relit les sites des compagnies, repère les nouvelles offres, garde celles qui
  concernent un poste PNC, leur donne une note sur 100 et vous les envoie.
- Elle vous prévient aussi si un site change au point de ne plus pouvoir être lu (« source en panne »).

> 🔒 Le dépôt est **public**. Vos informations personnelles (profil, adresses, jetons) ne vont **jamais** dans les
> fichiers du dépôt : elles se rangent dans les **secrets** GitHub, invisibles pour les visiteurs.

---

## Sommaire

1. [Autoriser le workflow à enregistrer son état](#1-autoriser-le-workflow-à-enregistrer-son-état)
2. [Créer vos canaux de notification](#2-créer-vos-canaux-de-notification)
3. [Ajouter les secrets dans GitHub](#3-ajouter-les-secrets-dans-github)
4. [Remplir votre profil (PROFILE_YAML)](#4-remplir-votre-profil-profile_yaml)
5. [Lancer le premier run à la main](#5-lancer-le-premier-run-à-la-main)
6. [Lire le résumé d'un run](#6-lire-le-résumé-dun-run)
7. [Comprendre les notifications et le score](#7-comprendre-les-notifications-et-le-score)
8. [Vérifier que tout marche](#8-vérifier-que-tout-marche)
9. [Sources surveillées](#9-sources-surveillées)
10. [Dépannage](#10-dépannage)
11. [Pour les développeurs](#11-pour-les-développeurs)

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

Les offres « 🟢 Très pertinent » arrivent en priorité haute (son + bannière), les « 🟡 À regarder » en priorité
normale. Chaque notification a un bouton **Ouvrir l'offre**.

### 💬 Discord

1. Dans votre serveur Discord (créez-en un gratuitement si besoin : **+** dans la barre de gauche), faites un clic
   droit sur le salon qui recevra les offres → **Modifier le salon**.
2. **Intégrations** → **Webhooks** → **Nouveau webhook** → donnez-lui un nom (« Veille PNC »).
3. **Copier l'URL du webhook**. Valeur à garder → secret `DISCORD_WEBHOOK_URL`.

### ✈️ Telegram

1. Dans Telegram, ouvrez une conversation avec **@BotFather** (le compte officiel, avec la coche bleue).
2. Envoyez `/newbot`, choisissez un nom puis un identifiant se terminant par `bot` (ex. `ma_veille_pnc_bot`).
3. BotFather répond avec un **jeton** du type `123456789:AAH...` → secret `TELEGRAM_BOT_TOKEN`.
4. Ouvrez la conversation avec **votre** bot (lien donné par BotFather) et envoyez-lui un message, par exemple
   « bonjour ».
5. Dans un navigateur, ouvrez `https://api.telegram.org/bot<JETON>/getUpdates` en remplaçant `<JETON>` par votre
   jeton. Repérez `"chat":{"id":` suivi d'un nombre (ex. `"chat":{"id":987654321`). Ce nombre → secret
   `TELEGRAM_CHAT_ID`.

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
| Profil | `PROFILE_YAML` | votre profil (étape 4) — facultatif mais conseillé |
| ntfy | `NTFY_TOPIC` | le nom de votre sujet |
| ntfy | `NTFY_SERVER` | facultatif, `https://ntfy.sh` par défaut |
| Discord | `DISCORD_WEBHOOK_URL` | l'URL du webhook |
| Telegram | `TELEGRAM_BOT_TOKEN` | le jeton donné par BotFather |
| Telegram | `TELEGRAM_CHAT_ID` | le nombre trouvé dans `getUpdates` |
| E-mail | `SMTP_HOST` | `smtp.gmail.com` |
| E-mail | `SMTP_PORT` | `465` |
| E-mail | `SMTP_USER` | votre adresse Gmail |
| E-mail | `SMTP_PASSWORD` | le mot de passe d'application (16 lettres) |
| E-mail | `EMAIL_TO` | l'adresse qui reçoit les alertes |

Un canal n'est activé que si **tous** ses secrets sont présents. Si un canal tombe en panne, les autres continuent.

---

## 4. Remplir votre profil (PROFILE_YAML)

Le profil sert à calculer le score de chaque offre. Copiez le modèle ci-dessous (il est aussi dans
[`profile.example.yaml`](profile.example.yaml)), adaptez les valeurs, et collez **tout le texte** dans un secret
nommé `PROFILE_YAML`. Respectez les espaces et les deux-points.

```yaml
cca: false                 # titulaire du CCA ? true = oui, false = non
english_level: B2          # A2 / B1 / B2 / C1 / C2
english_certified: false   # TOEIC / Linguaskills en cours de validité ?
experience_pnc_months: 0
experience_client_months: 12
bases_ok: ["Paris", "Orly", "Roissy", "CDG"]        # villes / aéroports qui vous conviennent
bases_maybe: ["Lyon", "Nice", "Marseille", "La Réunion"]
contracts_ok: ["CDI", "CDD", "Alternance", "Contrat de professionnalisation", "Saisonnier"]
min_score_to_notify: 40    # en dessous de ce score : pas de notification (mais visible dans le résumé)
```

Sans profil, tout fonctionne quand même : chaque offre PNC reçoit un score neutre de 50/100 et vous est envoyée.

Pour modifier votre profil plus tard : **Settings** → **Secrets and variables** → **Actions** → crayon ✏️ à côté de
`PROFILE_YAML`.

---

## 5. Lancer le premier run à la main

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

## 6. Lire le résumé d'un run

**Actions** → cliquez sur un run → le **résumé** s'affiche sous le schéma du job :

| Colonne | Signification |
|---|---|
| Source | identifiant de la source (voir section 9) |
| Statut | `ok`, `ok (changement)` pour une page surveillée qui a changé, `❌ …` en cas d'échec, `⏸ en pause` si le site refuse l'accès |
| Offres | nombre d'offres actuellement en ligne sur cette source (`page` pour une page surveillée) |
| Nouvelles | offres apparues depuis le run précédent |

En dessous : les offres PNC notifiées, l'état de chaque canal (✅ / ❌ avec la raison), et des **notes** (offres PNC
sous votre seuil, postes d'instructeur PNC, nettoyage de l'état…).

Un commit « chore(état): mise à jour de la veille » apparaît dans l'historique quand l'état change : c'est normal,
c'est la mémoire de la veille (et ces commits empêchent GitHub de désactiver le workflow après 60 jours).

---

## 7. Comprendre les notifications et le score

| Message | Quand |
|---|---|
| 🟢 / 🟡 *Compagnie — Intitulé* | Nouvelle offre PNC dont le score atteint votre seuil (au-delà de 5 offres dans le même run : un message groupé) |
| 📣 *Compagnie : la page recrutement PNC a changé* | Une page « campagne » surveillée a changé, avec un extrait du nouveau texte |
| ⚠️ *Source en panne* | Une source échoue 3 fois de suite (une seule alerte, pas de spam) |
| ✅ *Source rétablie* | La source fonctionne de nouveau |
| 📊 *Résumé de la semaine* | Le lundi matin : offres vues par source et état des sources (preuve que la veille tourne) |

**Score sur 100** (les raisons sont listées dans chaque notification) :

| Critère | Points |
|---|---|
| Poste PNC détecté | base 50 |
| Lieu dans `bases_ok` / `bases_maybe` / non précisé / hors liste | +25 / +10 / +5 / −20 |
| Contrat dans `contracts_ok` | +10 |
| CCA exigé alors que vous ne l'avez pas | −30 |
| Annonce « sans CCA » ou « CQP » (si vous n'avez pas le CCA) | +15 |
| Niveau d'anglais exigé supérieur au vôtre, ou certification demandée sans certification | −15 |

≥ 70 : 🟢 Très pertinent · 40 à 69 : 🟡 À regarder · < 40 : ⚪ Peu pertinent.
Si l'annonce est trop courte pour juger des exigences, elle n'est pas pénalisée et porte la mention « à vérifier ».

**Détection PNC** : l'intitulé (ou, à défaut, la description) doit contenir un terme comme *PNC*, *hôtesse de
l'air*, *steward*, *cabin crew*, *chef de cabine*… et l'intitulé ne doit pas contenir de terme d'exclusion
(*pilote*, *mécanicien cabine*, *planning PN*, *stage*, *directeur*, *hôtesse d'accueil*…). Les postes
d'*instructeur PNC* sont classés à part : ils apparaissent dans les notes du résumé, sans notification.

---

## 8. Vérifier que tout marche

- **Test d'une notification** : ouvrez `data/state.json` dans GitHub (crayon ✏️), supprimez une entrée d'offre PNC
  (le bloc entre accolades qui commence par `"airfrance_pn::…"` par exemple, virgule comprise), validez
  (*Commit changes*), puis relancez le workflow à la main : l'offre est vue comme nouvelle et vous est envoyée sur
  chaque canal. *(S'il n'y a aucune offre PNC en ligne, supprimez n'importe quelle offre : elle sera réindexée sans
  notification, ce qui prouve au moins que la détection fonctionne.)*
- **Test d'une source en panne** : dans `config/sources.yaml`, remplacez l'URL d'une source par une adresse
  invalide. Après 3 runs, vous recevez une alerte « ⚠️ Source en panne », une seule fois. Remettez l'URL : vous
  recevez « ✅ Source rétablie ».

---

## 9. Sources surveillées

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

### Sources désactivées

Deux sources prévues sont **désactivées** (`enabled: false`) car ces sites bloquent les programmes automatiques.
La veille respecte ces protections et ne cherche pas à les contourner.

- **French Bee – page « recrutement PNC »** (`frenchbee_pnc`) : le site ne répond pas aux robots. C'est pourtant là
  que French Bee annonce ses campagnes PNC. **Alternative** : une alerte Google, lue comme un flux.
  1. Ouvrez <https://www.google.com/alerts>, tapez `"French Bee" PNC recrutement`.
  2. **Afficher les options** → *Fréquence* : « Au fil de l'eau » ; *Distribuer à* : **Flux RSS** → **Créer**.
  3. Cliquez sur l'icône RSS de l'alerte et copiez l'adresse de la page.
  4. Ajoutez à la fin de `config/sources.yaml` (en respectant l'indentation) :
     ```yaml
       - id: frenchbee_alerte
         company: French Bee (alerte Google)
         type: rss
         url: "COLLEZ ICI L'ADRESSE DU FLUX"
     ```
  Le même procédé fonctionne pour toute compagnie sans page carrières (ex. Corsair).
- **Air Austral** (`airaustral`) : le site renvoie « accès refusé » (protection Cloudflare). Même alternative
  possible : une alerte Google `"Air Austral" recrutement PNC`.

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
dont l'intitulé ou le lieu contient un de ces mots. Une source ajoutée plus tard est initialisée silencieusement,
comme au premier lancement.

---

## 10. Dépannage

| Problème | Solution |
|---|---|
| Aucun message reçu | Vérifiez dans le résumé du run la ligne **Canaux** : un ❌ indique la raison. Vérifiez le nom exact des secrets. |
| E-mail : « authentification SMTP refusée » | Utilisez un **mot de passe d'application** Gmail, collé sans espaces. |
| Telegram : HTTP 400 ou 403 | `TELEGRAM_CHAT_ID` incorrect, ou vous n'avez pas encore écrit à votre bot. |
| Le run échoue à l'étape « Enregistrer l'état » | Revoyez l'étape 1 (*Read and write permissions*). |
| Une source est « ❌ » | Si c'est passager, rien à faire. Après 3 échecs vous recevez une alerte : le site a sans doute changé et `config/sources.yaml` doit être adapté. |
| Le workflow ne tourne plus | GitHub coupe les workflows programmés après 60 jours sans activité : onglet **Actions** → **Veille PNC** → **Enable workflow**. Normalement les commits d'état l'évitent. |
| Je veux repartir de zéro | Remplacez le contenu de `data/state.json` par `{}` : le run suivant refait une initialisation silencieuse. |

---

## 11. Pour les développeurs

```bash
python -m venv .venv && .venv/Scripts/activate          # Windows (Linux/macOS : source .venv/bin/activate)
pip install -r requirements-dev.txt -r requirements-browser.txt
python -m playwright install chromium

export PYTHONPATH=src                                    # PowerShell : $env:PYTHONPATH="src"
python -m pytest -q                                      # tests (fixtures enregistrées, sans réseau)
python -m veille --dry-run                               # tout tester : aucune notification, état non modifié
python -m veille --dry-run --source transavia            # une seule source (même désactivée)
python -m veille --dry-run --profile profile.yaml        # avec un profil local (profile.yaml est ignoré par git)
python -m veille --weekly --dry-run                      # aperçu du résumé hebdomadaire
```

Architecture : `src/veille/main.py` orchestre *relève → diff → filtre → score → notifie → sauvegarde* ;
`sources/` contient un module par **type** de source, `matching.py` la détection PNC et le score, `state.py` l'état,
`notifiers/` les canaux. Politesse : User-Agent explicite, délai de 20 s, 2 tentatives maximum, une requête à la
fois par domaine ; un site qui répond 403/429 est mis en pause 6 h après 3 refus, sans insister.

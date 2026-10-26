# Brief – Veille automatique des offres PNC

> À l'attention de Claude Code. Ce document décrit le système à construire dans ce dépôt (`veille-pnc`). Lis-le en entier avant d'écrire du code, puis propose un plan court avant de te lancer.

## 1. Objectif

Être prévenu **le plus vite possible** (cible : < 20 min) dès qu'une offre de **PNC** (hôtesse de l'air / steward / personnel navigant commercial) est publiée par une compagnie aérienne **basée en France ou en outre-mer**, et savoir si elle **correspond à mon profil**.

Le système :
1. relève périodiquement les sources listées en §4 ;
2. détecte les **nouvelles** offres (ou les changements de pages « campagne ») ;
3. filtre celles qui concernent un poste PNC et leur attribue un score selon mon profil ;
4. envoie une notification sur **plusieurs canaux** (Discord, téléphone via ntfy, Telegram, e-mail) ;
5. me prévient aussi si une source **tombe en panne** (site refait, plus rien de lisible).

**Contrainte absolue : 100 % gratuit.** Pas de service payant, pas de serveur à louer.

## 2. Environnement d'exécution

- **GitHub Actions**, dépôt **public** (minutes illimitées sur les runners Linux standard).
- Langage : **Python 3.12**.
- Planification : `cron: "7,22,37,52 * * * *"` (toutes les 15 min, en évitant les heures pile où GitHub retarde les exécutions) + `workflow_dispatch` pour lancer à la main.
- `concurrency: { group: veille-pnc, cancel-in-progress: false }` pour éviter deux exécutions en parallèle.
- **État persistant** : un fichier `data/state.json` commité par le workflow après chaque exécution (`permissions: contents: write`, message de commit avec `[skip ci]`). Ces commits servent aussi à éviter la désactivation automatique des workflows programmés après 60 jours d'inactivité sur un dépôt public. Ne commiter que si l'état a changé, **sauf** un commit de « heartbeat » au moins une fois par semaine.
- Les secrets (webhooks, jetons, mots de passe) vont dans **GitHub Secrets**, jamais dans le code ni dans les logs.
- Le dépôt étant public : **aucune donnée personnelle** dans le code ou la config commitée. Le profil (§6) est lu depuis un secret `PROFILE_YAML` ; un `profile.example.yaml` sert de modèle.
- Garder les exécutions courtes : cache pip, et cache du navigateur Playwright (`~/.cache/ms-playwright`). N'installer Playwright que si une source activée en a besoin.

## 3. Architecture attendue

```
veille-pnc/
├── .github/workflows/veille.yml
├── src/veille/
│   ├── main.py              # orchestration : fetch → diff → filtre → score → notifie → sauvegarde
│   ├── models.py            # dataclass Offer
│   ├── sources/             # un module par TYPE de source (pas par compagnie)
│   │   ├── base.py          # interface Source.fetch() -> list[Offer]
│   │   ├── rss.py           # flux RSS génériques (Talentsoft, Taleo)
│   │   ├── html_list.py     # listes HTML rendues côté serveur (sélecteurs CSS en config)
│   │   ├── sitemap.py       # diff des URLs d'un sitemap + rendu de la page offre
│   │   ├── browser.py       # pages rendues en JS (Playwright)
│   │   └── page_watch.py    # détection de changement d'une zone de page (hash du texte normalisé)
│   ├── matching.py          # détection PNC + scoring profil
│   ├── state.py             # lecture/écriture data/state.json
│   └── notifiers/           # discord.py, ntfy.py, telegram.py, email.py
├── config/sources.yaml      # déclaration des sources (cf. §4) – ajout d'une compagnie = ajout de config
├── profile.example.yaml
├── data/state.json
├── tests/                   # pytest, avec fixtures HTML/XML enregistrées
└── README.md                # installation pas à pas pour un non-développeur
```

Modèle `Offer` : `source_id`, `company`, `offer_id` (stable), `title`, `url`, `location`, `contract`, `published_at` (si dispo), `description` (texte brut tronqué), `raw` (dict). L'identifiant de déduplication = `source_id + offer_id` (à défaut, l'URL normalisée).

## 4. Sources (audit du 26/10/2026)

Toutes les URLs ci-dessous ont été vérifiées manuellement. **Vérifie-les à nouveau** au début (les sites changent) et adapte les parseurs si besoin.

| id | Compagnie | Type | URL / méthode |
|---|---|---|---|
| `airfrance_pnc` | Air France | `rss` | `https://recrutement.airfrance.com/handlers/offerRss.ashx?LCID=1036&Rss_Profile=3416` (profil PNC) |
| `airfrance_pn` | Air France | `rss` | `…/offerRss.ashx?LCID=1036&Rss_JobFamily=3383` (famille Personnel Navigant, filet de sécurité) |
| `hop` | HOP! | `rss` | `…/offerRss.ashx?LCID=1036&Rss_CustomCodeTableItem=4483` |
| `aircalin` | Aircalin | `rss` | `https://carrieres.aircalin.com/handlers/offerRss.ashx?LCID=1036&Rss_JobFamily=6827` (famille PNC) |
| `easyjet` | easyJet | `rss` | `https://easyjet.taleo.net/careersection/feed/joblist.rss?lang=en&portal=101430233&searchtype=3&f=null&s=5|A&a=null&multiline=true` – ne contient que les ~10 dernières offres, filtrer sur cabin crew + lieu en France |
| `transavia` | Transavia France | `html_list` | `https://recrutement.transavia.com/fr/annonces` (DigitalRecruiters, ~40 offres, paginé par 20). **À vérifier** : rendu serveur ou JS ? Sinon basculer en `browser`. Les offres Transavia ne passent **pas** par le site Air France. |
| `airtahitinui` | Air Tahiti Nui | `html_list` | `https://fr.airtahitinui.com/emploi/offres` (Drupal, rendu serveur ; texte « Aucune offre d'emploi n'est disponible » quand vide) |
| `asl` | ASL Airlines France | `html_list` | `https://cezanneondemand.intervieweb.it/aslaviationgroup/en/career` (liste avec « Functional Area » ; garder les offres en France, la catégorie « Aircrew » en priorité) |
| `aircaraibes` | Air Caraïbes | `sitemap` | `https://recrutement.aircaraibes.com/sitemap.xml` → URLs `/offer/…` ; page offre rendue en JS (Hellowork) → titre via Playwright, uniquement pour les **nouvelles** URLs |
| `frenchbee_ats` | French Bee | `sitemap` | `https://recrutement.frenchbee.com/sitemap.xml` (même plateforme Hellowork) |
| `frenchbee_pnc` | French Bee | `page_watch` | `https://www.frenchbee.com/fr/recrutement` (redirige vers `/fr/recrutement-pnc`). **Source critique** : les campagnes PNC sont annoncées ici et non dans l'ATS. Hasher le texte du contenu principal ; notifier avec un extrait du nouveau texte. |
| `aircorsica` | Air Corsica | `browser` | `https://aircorsica-rh.my.salesforce-sites.com/Recrutement` (Salesforce Sites, rendu JS ; la liste affiche titre, direction, contrat, date, ville) |
| `airaustral` | Air Austral | `page_watch` | `https://www.air-austral.com/a-propos-dair-austral/recrutement.html` (page statique avec onglets ; hasher uniquement la zone de contenu, pas l'en-tête/menus dynamiques) |
| `corsair` | Corsair | — | Pas de page carrières trouvée. Phase 2 : API France Travail (§9). |

Règles de politesse : un User-Agent explicite (`veille-pnc/1.0 (+URL du dépôt)`), timeout de 20 s, 2 tentatives maximum avec délai, **une requête à la fois par domaine**, pas de contournement de protections anti-bot. Si un site renvoie 403/429 de façon répétée, désactiver la source et notifier plutôt qu'insister.

## 5. Détection des postes PNC

Une offre est « PNC » si son titre (prioritairement) ou sa description contient un terme positif **et** aucun terme d'exclusion dans le titre. Normaliser (minuscules, sans accents) avant de comparer.

- **Positifs** : `pnc`, `personnel navigant commercial`, `personnel commercial navigant`, `hotesse de l'air`, `hotesse`, `steward`, `cabin crew`, `flight attendant`, `chef de cabine`, `cqp pnc`, `cabin manager`, `pnc stagiaire`.
- **Exclusions (titre)** — exemples réels rencontrés pendant l'audit : `mecanicien cabine` (Air France), `planification personnels navigants` (Air Corsica), `regulation pn` / `planning pn` / `logistique pn` / `support production pn` (Transavia), plus `pilote`, `officier pilote`, `instructeur` (sauf `instructeur pnc` : à classer à part), `directeur`, `stage`.
- Les sources `page_watch` ne produisent pas d'offres : tout changement significatif déclenche une notification « campagne possible » (cf. §7).

Écris des tests unitaires avec ces exemples (positifs et faux positifs).

## 6. Scoring selon le profil

Le profil est lu depuis le secret `PROFILE_YAML` (structure dans `profile.example.yaml`). **Je n'ai pas encore fourni mes valeurs** : mets des valeurs d'exemple dans le fichier modèle et fais en sorte que tout fonctionne même sans profil (score neutre).

```yaml
# profile.example.yaml
cca: false                 # titulaire du CCA ?
english_level: B2          # A2 / B1 / B2 / C1 / C2
english_certified: false   # TOEIC / Linguaskills valide ?
experience_pnc_months: 0
experience_client_months: 12
bases_ok: ["Paris", "Orly", "Roissy", "CDG"]        # villes / aéroports acceptés
bases_maybe: ["Lyon", "Nice", "Marseille", "La Réunion"]
contracts_ok: ["CDI", "CDD", "Alternance", "Contrat de professionnalisation", "Saisonnier"]
min_score_to_notify: 40    # en dessous : pas de notification (mais logué)
```

Score sur 100, explicable (garder la liste des raisons pour l'afficher dans la notification) :
- Poste PNC détecté : base 50.
- Lieu dans `bases_ok` : +25 ; dans `bases_maybe` : +10 ; lieu inconnu : +5 ; hors liste : −20.
- Contrat dans `contracts_ok` : +10 ; contrat inconnu : 0.
- L'annonce exige le CCA (`cca`, `cabin crew attestation`) alors que `cca: false` : −30 ; l'annonce dit « sans CCA » / « CQP » : +15 si `cca: false`.
- Niveau d'anglais exigé (B2, TOEIC 750/800…) supérieur à celui du profil, ou certification exigée sans certification : −15.
- Libellés : ≥ 70 « 🟢 Très pertinent », 40–69 « 🟡 À regarder », < 40 « ⚪ Peu pertinent ».

Si une offre PNC est trop courte pour être évaluée (titre seul), ne pas pénaliser : marquer « à vérifier ».

## 7. Notifications

Chaque canal est **optionnel** et activé seulement si ses secrets existent. Un canal en échec ne doit pas bloquer les autres (log + alerte dans le résumé du run).

| Canal | Secrets | Notes |
|---|---|---|
| Discord | `DISCORD_WEBHOOK_URL` | Embed : compagnie, titre (lien), lieu, contrat, score + raisons. |
| ntfy (téléphone) | `NTFY_TOPIC` (+ `NTFY_SERVER`, défaut `https://ntfy.sh`) | Le nom du topic doit être long et aléatoire (un topic public est lisible par qui le devine). Priorité haute pour 🟢, normale pour 🟡. Bouton « Ouvrir l'offre ». |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Message HTML court + lien. |
| E-mail | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO` | Gmail avec mot de passe d'application. Plusieurs offres d'un même run = un seul e-mail récapitulatif. |

Types de messages :
1. **Nouvelle offre PNC** (score ≥ seuil) — un message par offre, groupé si > 5 offres dans le même run.
2. **Changement de page campagne** (`page_watch`) — « 📣 French Bee : la page recrutement PNC a changé » + extrait du nouveau texte (les lignes ajoutées).
3. **Source en panne** — si une source échoue ou renvoie 0 élément lisible alors qu'elle en avait avant, pendant **3 runs consécutifs** : une seule alerte, puis une alerte « rétablie » quand elle revient. Ne pas spammer.
4. **Résumé hebdomadaire** (optionnel, le lundi matin heure de Paris) : nombre d'offres vues par source, état des sources. Sert aussi de preuve de vie.

## 8. Comportements importants

- **Premier lancement = initialisation silencieuse** : enregistrer toutes les offres existantes comme « déjà vues » sans notifier, puis envoyer un seul message « ✅ Veille PNC active – N offres indexées, dont X PNC » (avec la liste des offres PNC déjà en ligne). Même règle quand une nouvelle source est ajoutée.
- Mode `--dry-run` (pas de notification, pas d'écriture d'état, affichage console) et `--source <id>` pour tester une seule source en local.
- Purger de l'état les offres non revues depuis 90 jours.
- Les erreurs d'une source n'interrompent jamais le run.
- Résumé lisible dans le **job summary** GitHub (`$GITHUB_STEP_SUMMARY`) : tableau sources / statut / nb d'offres / nouvelles.

## 9. Phase 2 (après la phase 1 validée)

- **API France Travail** (gratuite, inscription sur francetravail.io) : recherche par mots-clés PNC, code ROME `G1803` (personnel navigant commercial) — couvre Corsair et sert de filet de sécurité.
- Compagnies supplémentaires à étudier : Air Tahiti (domestique), Air Calédonie, Air Saint-Pierre, Chalair, Amelia, La Compagnie, Ewa Air, Air Antilles.
- easyJet : si le flux RSS ne suffit pas (10 offres max), interroger la recherche Taleo filtrée sur la France.

## 10. Livrables et critères d'acceptation (phase 1)

1. Le workflow tourne toutes les 15 min sur GitHub Actions et chaque run dure **moins de 3 minutes**.
2. Toutes les sources du §4 (sauf Corsair) renvoient des offres ou un état cohérent, vérifié en `--dry-run`.
3. Une fausse offre injectée dans l'état (supprimer une entrée de `state.json`) déclenche bien une notification sur chaque canal configuré.
4. Les faux positifs du §5 sont exclus (tests pytest verts dans le workflow CI sur push).
5. Une source volontairement cassée (URL invalide) déclenche l'alerte « source en panne » après 3 runs, une seule fois.
6. `README.md` en français, pour un non-développeur : créer chaque canal de notification (webhook Discord, appli ntfy, bot Telegram, mot de passe d'application Gmail), ajouter les secrets, remplir `PROFILE_YAML`, lancer le premier run à la main, lire le résumé.

Travaille par petites étapes vérifiables : d'abord `rss` + Discord + état + workflow, puis les autres types de sources, puis les autres canaux, puis le scoring fin. Commite à chaque étape.

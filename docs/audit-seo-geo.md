# Audit SEO + GEO — everbook-album.com

*Audit en lecture seule du 12 novembre 2026. Aucun fichier du site n'a été modifié, rien n'a été déployé.*

**Comment l'audit a été fait :**

- **Le site en prod**, vu comme le voit un robot, sans JavaScript (requêtes avec l'en-tête « Googlebot » et sans suivre les redirections) :
  - les 20 pages du sitemap ;
  - 25 autres adresses : pages de l'application, adresses qui n'existent pas, fichiers.
- **Le code** de la branche `dev`, identique à la prod au moment de l'audit (dernier commit `c59e5cf`).
- **Des tests dans un vrai navigateur** (Playwright + axe-core 4.10.2) pour l'accessibilité et la vitesse.

**Outils SEO :** aucune skill SEO/GEO n'est installée dans cette session. Les appels à `claude-site-audit:site-audit` et `seo-audit` renvoient « Unknown skill ». La méthode demandée a donc été suivie à la main. Les scripts utilisés (`crawl.py`, `audit.py`, `a11y.js`, `perf.js`) sont dans le dossier de travail de la session, pas dans le dépôt.

**Légende :**

- **VÉRIFIÉ** : constaté dans le HTML servi en prod, ou en lançant le code.
- **NON VÉRIFIÉ** : impossible à contrôler d'ici. La raison est donnée.
- **Gravité :** Haute / Moyenne / Basse.
- **Effort :** XS (moins de 30 min), S (moins de 2 h), M (une demi-journée).

---

## 1. Résumé en 5 lignes

1. La technique est saine : HTTPS, pages publiques pré-rendues en HTML, canonical et hreflang corrects, sitemap conforme aux routes, robots IA autorisés, réponses en 130 à 330 ms, LCP mobile à 1,7 s.
2. **Le blocage n°1 n'est pas dans le code** : la marque ne ressort pas dans les résultats de recherche. Il faut déclarer le site à Google et à Bing, et lui obtenir des liens externes.
3. **Les prix des albums ne sont visibles sur aucune page publique.** On ne les trouve que dans le JSON-LD et dans `llms.txt`. C'est incohérent pour Google, et une IA ne peut pas les citer depuis une page.
4. Il y a des trous dans ce que lisent les robots :
   - l'accueil anglais est servi sans la galerie des 20 modèles ;
   - toute adresse inconnue répond « 200 » avec une page vide ;
   - les 3 pages thématiques (voyage, couple, famille) ne sont liées ni depuis l'accueil, ni depuis le menu, ni depuis le pied de page.
5. Accessibilité : il manque les étiquettes reliées aux champs des formulaires (contact, inscription), un lien « Aller au contenu », les textes alternatifs des 20 couvertures, et un texte sur /gift n'a pas assez de contraste.

---

## 2. Tableau des constats

### 2.1 Technique

| # | Constat | Statut | Preuve | Gravité | Effort |
|---|---|---|---|---|---|
| T1 | Les 20 pages du sitemap répondent **200** en 130 à 330 ms, servies depuis le cache Vercel (`x-vercel-cache: HIT`). | VÉRIFIÉ | `crawl.py` : `200 486ms 30940B HIT … /` … `200 216ms … /fr/privacy` | — | — |
| T2 | **Fausse page 404** : `/pricing`, `/doesnotexist-xyz`, `/fr/doesnotexist` et `/FAQ` répondent **200** avec la coquille vide de l'application (3 085 octets). Cette coquille n'a ni canonical, ni `noindex`, et son `og:url` pointe vers l'accueil. | VÉRIFIÉ | `crawl.py` : `200 189ms 3085B … canon=[] /pricing \| Everbook — your photos, as a printed book`. Cause : `frontend/vercel.json:63-68` renvoie toute adresse vers `/app`, et `frontend/scripts/prerender.mjs:129` écrit `app.html` = `index.html` sans `noindex`. La page 404 n'existe que côté navigateur (`src/App.jsx:280`). | Moyenne | XS |
| T3 | Les pages de l'application (`/auth`, `/dashboard`, `/cart`, `/create`, `/editor/…`) répondent 200 avec la même coquille vide. Elles sont bloquées dans robots.txt, sauf **`/auth`**, qui reste explorable et n'a pas de `noindex`. | VÉRIFIÉ | `crawl.py` : `200 … /auth`. Liste des chemins bloqués : `frontend/seo.plugin.js:15` (`/auth` absent). | Basse | XS |
| T4 | Redirections propres en **308** : `http://` → `https://`, `/returns` → `/terms`, `/index.html` → `/` et `/faq.html` → `/faq`. `/faq/` et `/fr/` répondent 200 avec le bon canonical (sans la barre finale). | VÉRIFIÉ | `curl -sSI http://everbook-album.com/` → `308 … location: https://everbook-album.com/`. `crawl.py` : `308 loc=/terms /returns`. | — | — |
| T5 | `www.everbook-album.com` n'a pas pu être testé : le proxy de la session refuse cet hôte. | NON VÉRIFIÉ | `curl https://www.everbook-album.com/` → `CONNECT tunnel failed, response 403` (le proxy, pas le site). | Moyenne | XS (à toi) |
| T6 | Pré-rendu : toutes les pages publiques sont servies **en HTML complet**, avec texte, titre, description et liens. Les autres adresses sont rendues dans le navigateur. | VÉRIFIÉ | `frontend/scripts/prerender.mjs:131-140`. `audit.py` : `words=261…3666` sur les pages publiques, `words=9` sur la coquille. | — | — |
| T7 | **Pas de risque de `noindex` venant de dev ou des aperçus** : seule une build Vercel `production` est indexable. Les autres ont `Disallow: /` et la balise `noindex, nofollow`. La prod n'a ni `X-Robots-Tag` ni balise meta robots. | VÉRIFIÉ | `frontend/seo.plugin.js:21-25` et `:46`. Simulation : `preview → indexable:false, "Disallow: /"`, `production → indexable:true`. `crawl.py` : `xr=None meta=[]` sur les 20 pages. | — | — |
| T8 | Le site **dev** est-il un projet Vercel séparé déployé en « production » ? Si oui, il serait indexable (même règle que T7). | NON VÉRIFIÉ | Aucune adresse du site dev dans le dépôt (`grep vercel.app` → rien). À contrôler : `<adresse dev>/robots.txt` doit afficher `Disallow: /`. | Haute si c'est le cas | XS (à toi) |
| T9 | Le sitemap correspond exactement aux routes publiques : 10 pages × EN/FR = 20 URL, chacune avec ses hreflang. Aucune page privée n'y figure. | VÉRIFIÉ | `frontend/src/lib/localePath.js:9-20` = `frontend/src/prerender.jsx:16-27` = les 20 `<loc>` de `/sitemap.xml`. | — | — |
| T10 | En-têtes HTTP corrects : HSTS (2 ans), `nosniff`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, et les fichiers `/assets/` en cache immuable. | VÉRIFIÉ | `curl -sSI https://everbook-album.com/` ; `frontend/vercel.json:7-58` | — | — |
| T11 | IndexNow est en place : la clé est publiée et chaque build de prod signale les pages modifiées (utilisé par Bing). | VÉRIFIÉ | `curl …/1475f9e5223540dbb7666ce28ddf663a.txt` → 200 ; `frontend/scripts/prerender.mjs` (dernières lignes) | — | — |

### 2.2 Contenu des pages (on-page)

| # | Constat | Statut | Preuve | Gravité | Effort |
|---|---|---|---|---|---|
| O1 | **L'accueil anglais est servi sans la section « Templates »** : 0 lien `/create?template=` et 1 seule image. La version française en a 21 et 22. La section n'apparaît qu'après le JavaScript. Cause : la galerie est chargée à la demande (`lazy`). L'anglais est pré-rendu en premier, avant que ce chargement soit terminé, et il garde donc le bloc d'attente vide. | VÉRIFIÉ | `crawl.py` : liens de `/` = 10, sans aucun `/create?template=` ; liens de `/fr` = 31. HTML de `/` : `<div class="min-h-[600px]"></div>` à la place de la galerie. Playwright après JS : `template links = 21`. Code : `frontend/src/pages/Landing.jsx:17` et `:172-177`, ordre de rendu `frontend/scripts/prerender.mjs:131` (EN avant FR). | Haute | S |
| O2 | **Pages quasi orphelines** : `/travel-photo-book`, `/couple-photo-album` et `/family-photo-album` (et leur version FR) ne reçoivent que **2 liens internes**, venant les unes des autres. Les autres pages en reçoivent 10. | VÉRIFIÉ | `crawl.py` : `INBOUND … 2 /travel-photo-book`. `grep occasion\|travel-photo-book` dans `TopNav.jsx`, `Footer.jsx` et `Landing.jsx` → aucun résultat. | Haute | XS |
| O3 | Aucun lien `<a>` ne relie une page à sa version dans l'autre langue : le sélecteur EN/FR est un `<button>`. Le hreflang compense pour Google, mais un robot qui suit les liens ne trouve pas les pages FR depuis les pages EN. | VÉRIFIÉ | `frontend/src/components/LanguageSwitcher.jsx:33-42`. `crawl.py` : aucune page EN ne lie `/fr…`. | Basse | XS |
| O4 | Le bouton principal « Create my album » est un `<button>` (accueil et pages thématiques), pas un lien. Les robots et beaucoup d'agents ne voient donc aucun chemin vers l'inscription depuis ce bouton. Seul le lien « Sign in » (`/auth?mode=login`) existe. | VÉRIFIÉ | `frontend/src/pages/Landing.jsx:72-79` et `:188-195` ; `frontend/src/pages/OccasionPage.jsx:28-35` ; Playwright : `BUTTON:landing-cta, BUTTON:footer-cta` | Moyenne | XS |
| O5 | **Titres sans « Lebanon / Liban »** : 0 des 20 titres contient le pays, alors que la clientèle est uniquement au Liban. Certains titres sont très courts : « Shipping — Everbook » (19 caractères), « Contact us — Everbook » (21). | VÉRIFIÉ | `audit.py` (titres) ; source : `frontend/src/locales/en.json:917+` et `fr.json:917+` (`meta.*.title`) | Moyenne | XS |
| O6 | Meta descriptions présentes, uniques et traduites partout. Longueur de 81 à 163 caractères. Shipping (81) est la plus faible. | VÉRIFIÉ | `audit.py` | Basse | XS |
| O7 | Un seul H1 par page partout. La page FAQ n'a **aucun H2/H3** : les 11 questions sont des `<button>`. | VÉRIFIÉ | `audit.py` : `/faq H1: ['Frequently asked questions'] \| H2 count 0` ; `frontend/src/pages/FAQPage.jsx:34-42` | Basse | XS |
| O8 | Contenu court : pages thématiques d'environ 255 à 280 mots, `/contact` 70, `/shipping` 140, `/gift` 225. | VÉRIFIÉ | `audit.py` : `words=…` | Moyenne | M (à toi : les textes) |
| O9 | Les pages EN et FR ne se copient pas l'une l'autre : chaque version est traduite et a son propre canonical. Petites traces d'anglais en FR : les noms des modèles (« Our Wedding », « Best Friends ») et le nom et la description des produits dans le JSON-LD de `/fr`. | VÉRIFIÉ | HTML de `/fr` : `…Utiliser ce modèleOur Wedding…` ; JSON-LD de `/fr` : `"name": "Everbook printed photo album — A5"` ; `frontend/src/lib/seoData.js:49-50` (texte EN figé) | Basse | S |

### 2.3 Hreflang

| # | Constat | Statut | Preuve | Gravité | Effort |
|---|---|---|---|---|---|
| H1 | Les 20 pages déclarent `en`, `fr` et `x-default` (= EN). Les liens sont réciproques : chaque page EN pointe vers sa FR et inversement. Chaque page s'inclut elle-même, et son canonical est identique à son URL hreflang. Le sitemap reprend les mêmes paires. | VÉRIFIÉ | `audit.py` : ex. `/fr/faq … canonical ['…/fr/faq'] \| hreflang [('en','…/faq'),('fr','…/fr/faq'),('x-default','…/faq')]` ; `frontend/scripts/prerender.mjs:80-84` ; `seo.plugin.js:31-41` | — | — |
| H2 | `<html lang>` et `og:locale` corrects : `en` + `en_US` sur la version anglaise, `fr` + `fr_FR` sur la version française. | VÉRIFIÉ | `grep og:locale` → `en_US` / `fr_FR` ; `audit.py` : `html lang: en / fr` | — | — |

### 2.4 Données structurées (schema)

| # | Constat | Statut | Preuve | Gravité | Effort |
|---|---|---|---|---|---|
| S1 | Tous les blocs JSON-LD sont syntaxiquement valides (`json.loads` réussi). Organization, WebSite et 2 Product (A5 et A4, 4 offres chacun) sont sur `/` et `/fr`. FAQPage (11 questions) est sur `/faq` et `/fr/faq`. Rien sur les 14 autres pages. | VÉRIFIÉ | Script de validation : `Product … offers: [('A5, 24 pages', 43), …]` | — | — |
| S2 | **Les prix du schema ne sont pas visibles sur la page qui les porte.** Les montants 43 / 63 / 83 / 113 / 53 / 73 / 99 / 129 n'apparaissent dans le texte visible d'**aucune** page. Google demande que les données structurées reflètent le contenu visible : une offre sans prix affiché risque d'être ignorée. | VÉRIFIÉ | Recherche de `\b43\b\|\b63\b\|\b113\b` dans le texte visible des 20 pages → 0 résultat. `/terms` dit seulement « depends on its format and on its number of pages ». `/gift` affiche les prix **livraison incluse** (« 24 p $ 58 … »). | Haute | S (dépend de ta décision) |
| S3 | Les prix sont identiques partout où ils figurent : `frontend/src/lib/pricing.js:38-40` (front), `backend/app/services/pricing.py:38-39` (en centimes), JSON-LD et `llms.txt`. Les prix de /gift = prix + 5 $ de livraison, ce qui est cohérent. | VÉRIFIÉ | Les deux tables de prix ; `llms.txt` : `A5 printed album $43 (24 pages), $63 …` | — | — |
| S4 | Le schema Product a ce que Google demande pour une fiche marchande : name, image, brand, offers (price, priceCurrency, availability), shippingDetails, hasMerchantReturnPolicy (`MerchantReturnNotPermitted`, cohérent avec `/terms`). Il manque des champs conseillés mais facultatifs : `sku`, `priceValidUntil`, et les avis (`aggregateRating`/`review`). | VÉRIFIÉ | Clés des offres : `['@type','areaServed','availability','hasMerchantReturnPolicy','name','price','priceCurrency','shippingDetails','url']` ; `frontend/src/lib/seoData.js:18-45` | Basse | XS |
| S5 | Organization : `sameAs` ne contient que Instagram. Il n'y a ni `contactPoint`, ni téléphone. Le logo est `favicon.png`, en 192×192 (le minimum de Google est 112×112, donc c'est correct). | VÉRIFIÉ | `frontend/scripts/prerender.mjs:108-111` | Moyenne | XS |
| S6 | FAQPage est valide, mais depuis 2023 Google n'affiche plus les FAQ enrichies que pour les sites gouvernementaux ou de santé. Elle reste utile pour les IA, sans gain d'affichage dans Google. | VÉRIFIÉ (code) | `frontend/src/lib/seoData.js:69-80` | Info | — |

### 2.5 Images et vitesse

| # | Constat | Statut | Preuve | Gravité | Effort |
|---|---|---|---|---|---|
| I1 | Toutes les images sont en WebP, de 5,6 à 98 Ko. Elles ont toutes `width` et `height`. L'image principale de l'accueil est chargée en priorité (`fetchPriority="high"`, `srcSet` 380/560/760), les autres en `loading="lazy"`. | VÉRIFIÉ | Script images : `44 balises img, no width 0, not lazy 3` (les 3 = image principale et son calque) ; `curl` : `98384 image/webp /hero-shelf-v2.webp` | — | — |
| I2 | **Les 20 couvertures de modèles ont `alt=""`.** Elles portent pourtant de l'information (le nom du modèle) et sont le seul contenu d'un lien. | VÉRIFIÉ | HTML de `/fr` : `<img src="/theme-covers/travel-beirut.webp" alt="" …>` ; `frontend/src/components/landing/TemplateGallery.jsx:21` | Moyenne | XS |
| I3 | Vitesse mesurée dans Chromium sur mobile (Pixel 7, 4G lente, processeur ralenti ×4) : accueil **LCP 1 656 ms**, CLS 0, environ 157 Ko transférés. `/fr/travel-photo-book` : LCP 544 ms. | VÉRIFIÉ | `perf.js` : `{"lcp":1656,"cls":0,"fcp":1192,"ttfb":126,"requests":16}` | — | — |
| I4 | Les vraies données de vitesse de Google (Chrome UX Report / PageSpeed) n'ont pas pu être lues. | NON VÉRIFIÉ | API PageSpeed → `429` (quota dépassé, sans clé) | — | — |

### 2.6 Accessibilité

| # | Constat | Statut | Preuve | Gravité | Effort |
|---|---|---|---|---|---|
| A1 | Les zones de la page (repères) sont présentes : `<header>`, `<nav>`, `<main>` et `<footer>`, chacun une fois. | VÉRIFIÉ | `grep -c '<main\|<nav\|<header\|<footer'` sur `/` et `/fr` → 1 chacun | — | — |
| A2 | **Pas de lien « Aller au contenu »** : la première touche Tab arrive sur le logo « Everbook », sur toutes les pages. | VÉRIFIÉ | `a11y.js` : `firstTab: A Everbook` ; `grep skip` → 0 ; `frontend/src/App.jsx:122-124` | Moyenne | XS |
| A3 | **Formulaires sans étiquette reliée** : 4 champs sur `/contact` et 3 sur l'inscription. Les `<label>` existent, mais sans `htmlFor` ni `id`. C'est classé « critical » par axe. | VÉRIFIÉ | `a11y.js` : `/contact [critical] label x4`, `/auth?mode=signup [critical] label x3` ; `frontend/src/pages/ContactPage.jsx:58-71` ; `frontend/src/pages/AuthPage.jsx:98-100` | Haute (a11y) | XS |
| A4 | Contraste insuffisant : texte corail `#e56b55` sur fond `#f9f8f6`, ratio **3,01** (il faut 4,5 pour un texte de 12 px), à 7 endroits de `/gift`, dont l'avis « bientôt disponible ». | VÉRIFIÉ | `a11y.js` : `/gift [serious] color-contrast x7` ; `frontend/src/pages/GiftPage.jsx:175` | Moyenne | XS |
| A5 | Le focus clavier est visible : contour natif `outline: auto` sur le premier élément. axe ne relève aucune autre erreur sur `/`, `/fr`, `/faq`, `/travel-photo-book` et `/shipping`. | VÉRIFIÉ | `a11y.js` : `outline=auto 1px`, aucune violation listée sur ces pages | — | — |

### 2.7 AEO / GEO (réponses pour les IA)

| # | Constat | Statut | Preuve | Gravité | Effort |
|---|---|---|---|---|---|
| G1 | **Marque introuvable** : une recherche « everbook-album.com » ou « Everbook album photo Liban » ne renvoie aucune page du site. | VÉRIFIÉ (avec le moteur de l'outil WebSearch, pas Google directement) | Résultats : theknot.com, everpresent.com, myalbum.com… aucun everbook-album.com | Haute | — (à toi) |
| G2 | Tous les robots IA et de recherche sont autorisés et reçoivent la page complète : GPTBot, OAI-SearchBot, ClaudeBot, PerplexityBot, Google-Extended, Googlebot, bingbot, CCBot → **200, 22 624 octets** sur `/faq`. robots.txt : `User-agent: * / Allow: /`, sans règle propre aux IA. | VÉRIFIÉ | Boucle `curl -A …` ; `/robots.txt` | — | — |
| G3 | `llms.txt` est complet et à jour : prix, pages, délais, zones, paiement, contact, FAQ. Il est généré à partir des mêmes données que le site, donc il ne peut pas les contredire. | VÉRIFIÉ | `/llms.txt` (5 283 octets) ; `frontend/src/lib/seoData.js:83-119` | — | — |
| G4 | Les réponses qu'une IA peut extraire **des pages** :<br>• délais : « ~3 days + 2 to 3 days », sur l'accueil, la FAQ, /shipping et /terms ;<br>• livraison : « USD 5 per order », sur /shipping et /terms ;<br>• formats : A4/A5, dans la FAQ.<br>Ce qu'elle ne trouve **sur aucune page** : le prix des albums (voir S2) et le papier (grammage, finition, couverture). | VÉRIFIÉ | Extraction du texte visible : `/shipping • Delivery within Lebanon costs USD 5 per order` ; recherche de `paper\|papier\|gsm\|mat\|glossy\|lamin` → 0 résultat sur les pages publiques | Haute (prix) / Moyenne (papier) | S |
| G5 | L'entité Everbook est cohérente : même nom, `alternateName` « Everbook Album », même e-mail et même Instagram dans le schema, le pied de page et `llms.txt`. Il manque les autres réseaux (TikTok…) et un téléphone ou WhatsApp, à la fois sur le site et dans le schema. | VÉRIFIÉ | `Footer.jsx:8,50-57` ; `prerender.mjs:104-112` ; `seoData.js:103` ; `grep 'tel:\|wa.me'` sur `/` et `/fr` → 0 | Moyenne | XS |

### 2.8 E-commerce

| # | Constat | Statut | Preuve | Gravité | Effort |
|---|---|---|---|---|---|
| E1 | **Limite de pages : 160, pas 200.** Le code fixe 160 pages au maximum (front et back), comme `llms.txt` et `/terms`. Ton brief parle de « 24 à 200 pages ». | VÉRIFIÉ | `frontend/src/lib/pricing.js:36` ; `backend/app/schemas.py:35` ; `llms.txt` : « 160 pages at most » | Moyenne (à trancher) | — |
| E2 | Disponibilité, livraison et retours sont cohérents entre le schema (`InStock`, LB, 3 + 2-3 jours, `MerchantReturnNotPermitted`), /shipping, /terms (réimpression si défaut, 14 jours) et `llms.txt`. L'option PDF est marquée « coming soon » partout, et retirée du schema tant que le paiement en ligne est inactif. | VÉRIFIÉ | `seoData.js:18-33, 55` ; texte de `/terms` et `/shipping` ; `llms.txt` | — | — |
| E3 | Le parcours de commande n'est pas explorable, et c'est voulu : tout passe par un compte. `/create`, `/cart` et `/order/` sont bloqués dans robots.txt et rendus dans le navigateur. Il n'existe aucune page publique « tarifs ». | VÉRIFIÉ | `seo.plugin.js:15` ; `crawl.py` : `/cart`, `/create` → coquille de 3 085 octets | Info | — |

### 2.9 Agents IA (un agent peut-il commander ?)

| # | Constat | Statut | Preuve | Gravité | Effort |
|---|---|---|---|---|---|
| AG1 | Un agent peut **comprendre** l'offre : `llms.txt`, la FAQ et /shipping donnent prix, délais et livraison. Pour **commander**, il doit :<br>1. créer un compte ;<br>2. confirmer son e-mail ;<br>3. téléverser des photos ;<br>4. passer par l'éditeur.<br>C'est impossible sans l'aide de la personne : c'est normal pour un produit fait à partir de ses propres photos. | VÉRIFIÉ (code) | `src/App.jsx:181-277` (`ProtectedRoute` sur toutes les étapes) | Info | — |
| AG2 | Ce qui gêne les agents qui lisent l'arbre d'accessibilité :<br>• les boutons d'action ne sont pas des liens (O4) ;<br>• les champs d'inscription n'ont pas d'étiquette reliée (A3) ;<br>• le sélecteur de langue est un bouton (O3). | VÉRIFIÉ | voir O4, A3, O3 | Moyenne | XS |

---

## 3. Top 10 des corrections (code) — **rien n'est appliqué avant ta validation, et tout passera d'abord par `dev`**

**1. Faire servir la galerie des modèles dans le HTML de l'accueil anglais** (O1, Haute)
- **Fichiers :** `frontend/src/prerender.jsx` et `frontend/scripts/prerender.mjs:131`
- **Changement :**
  1. Ajouter dans `prerender.jsx` une fonction exportée `warmUp()`. Elle fait un premier `renderToString` de `/`, puis attend la fin du chargement de la galerie : `await import("@/components/landing/TemplateGallery")` suivi d'une attente d'un tour (`setTimeout 0`).
  2. Appeler `await warmUp()` juste avant la boucle de `prerender.mjs:131`. Le composant `lazy` est alors déjà chargé quand l'anglais est rendu.
- **Vérifier :** `curl -s https://everbook-album.com/ | grep -c 'create?template='` doit afficher **21**, au lieu de 0.

**2. Dire « page introuvable » aux robots sur les adresses inconnues** (T2, T3, Moyenne)
- **Fichier :** `frontend/scripts/prerender.mjs:129`
- **Changement :** écrire `app.html` avec `<meta name="robots" content="noindex" />` ajouté dans `<head>`. Ça ne touche pas les 20 pages publiques, qui ont leurs propres fichiers. La coquille ne sert qu'aux pages privées et aux adresses inconnues.
- **Option plus complète, plus tard :** un vrai statut 404. Il faudrait lister les routes de l'application dans `vercel.json` à la place de la règle qui renvoie tout vers `/app`.
- **Vérifier :**
  - `curl -s https://everbook-album.com/pricing | grep noindex` doit trouver la balise ;
  - `curl -s https://everbook-album.com/faq | grep -c noindex` doit afficher **0**.

**3. Afficher les prix des albums sur une page publique** (S2, G4, Haute — **ta décision**, voir les questions)
- **Fichiers :** `frontend/src/locales/en.json` et `fr.json` (`faq.items`), et éventuellement `frontend/src/pages/Landing.jsx`
- **Changement, version minimale :** ajouter une question « How much does a photo album cost? / Combien coûte un album ? » dans la FAQ, avec la grille A5/A4 et la livraison à 5 $. Elle passe automatiquement dans le FAQPage et dans `llms.txt`.
- **Option :** un bloc de prix sur l'accueil, où se trouve le schema Product.
- **Vérifier :** `curl -s https://everbook-album.com/faq | grep -o '\$43'` doit trouver le prix (et le même pour `/fr/faq`).

**4. Relier les 3 pages thématiques au reste du site** (O2, Haute)
- **Fichiers :**
  - `frontend/src/components/Footer.jsx:25-34` : ajouter « Travel photo book », « Couple album » et « Family album » via `lp("/travel-photo-book")`… ;
  - éventuellement une ligne de liens sous le titre de la galerie dans `Landing.jsx`.
- **Vérifier :** relancer le comptage des liens entrants. Chaque page thématique doit en recevoir **au moins 10**, au lieu de 2.

**5. Mettre « Lebanon / Liban » dans les titres** (O5, Moyenne)
- **Fichiers :** `frontend/src/locales/en.json` et `fr.json`, bloc `meta` (ligne 917 et suivantes)
- **Exemples :**

| Page | Titre anglais proposé | Titre français proposé |
|---|---|---|
| Accueil | « Everbook — Photo Book in Lebanon, Laid Out for You » | « Everbook — Livre photo au Liban, mis en page pour vous » |
| Livraison | « Photo Book Delivery in Lebanon » | « Livraison au Liban » |
| Voyage | « Travel Photo Book, Printed in Lebanon » | — |

- **Vérifier :** `curl -s <url> | grep -o '<title>[^<]*'` sur les 20 pages.

**6. Relier les étiquettes aux champs des formulaires** (A3, Haute pour l'accessibilité)
- **Fichiers :** `frontend/src/pages/ContactPage.jsx:58-71` et `frontend/src/pages/AuthPage.jsx:98+`
- **Changement :** `<label htmlFor="contact-name">` avec `<input id="contact-name">`, et de même pour chaque champ (email, subject, message, name, password).
- **Vérifier :** relancer `a11y.js`. Il ne doit plus y avoir aucune violation `label` sur `/contact` ni sur `/auth?mode=signup`.

**7. Ajouter le lien « Aller au contenu »** (A2, Moyenne)
- **Fichiers :**
  - `frontend/src/App.jsx:122`, avant `<TopNav />` : `<a href="#main" className="sr-only focus:not-sr-only …">{t("a11y.skipToContent")}</a>` ;
  - `id="main"` sur les `<main>` des pages publiques ;
  - les textes dans `en.json` et `fr.json`.
- **Vérifier :** sur chaque page, la première touche Tab doit arriver sur « Skip to content / Aller au contenu ».

**8. Transformer les boutons « Create my album » en vrais liens** (O4, AG2, Moyenne)
- **Fichiers :** `frontend/src/pages/Landing.jsx:72-79` et `:188-195`, `frontend/src/pages/OccasionPage.jsx:28-35`
- **Changement :** remplacer `<button onClick=…>` par `<Link to={signedIn ? "/dashboard" : "/auth?mode=signup"}>`, avec la même apparence.
- **Vérifier :** `curl -s https://everbook-album.com/ | grep -o 'href="/auth?mode=signup"'` doit trouver le lien.

**9. Compléter l'entité Everbook dans le schema** (S5, G5, Moyenne)
- **Fichiers :**
  - `frontend/scripts/prerender.mjs:111` : `sameAs` avec TikTok et les autres comptes ;
  - `contactPoint` (`{"@type":"ContactPoint","contactType":"customer service","email":…,"telephone":…,"areaServed":"LB","availableLanguage":["en","fr"]}`) si tu me donnes un numéro ;
  - `frontend/src/lib/seoData.js:49-50` : nom et description des produits traduits sur `/fr` (O9).
- **Vérifier :** valider `/` et `/fr` dans le test des résultats enrichis de Google (https://search.google.com/test/rich-results). Aucune erreur, Organization avec plusieurs `sameAs`.

**10. Textes alternatifs des couvertures et contraste sur /gift** (I2, A4, Moyenne)
- **Fichiers :**
  - `frontend/src/components/landing/TemplateGallery.jsx:21` : `alt={t("landing.templates.coverAlt", { name: tpl.name })}`, par exemple « Photo book cover template: Beirut, Lebanon » ;
  - `frontend/src/pages/GiftPage.jsx:175` et les autres textes corail de 12 px : une couleur plus foncée, d'au moins 4,5:1 sur `#f9f8f6`.
- **Vérifier :**
  - `curl -s https://everbook-album.com/fr | grep -c 'alt=""'` doit afficher **1** (seul le calque décoratif de l'image principale) ;
  - `a11y.js` ne doit plus signaler de `color-contrast` sur `/gift`.

**Petits points qui pourront être ajoutés aux corrections ci-dessus :**

- ajouter `/auth` à la liste des pages bloquées (T3) ;
- transformer les questions de la FAQ en H2 (O7) ;
- mettre un lien `<a hreflang>` vers l'autre langue en plus du bouton (O3) ;
- ajouter `sku` aux offres (S4).

---

## 4. Qui fait quoi

### Ce que TOI tu dois faire (hors code)

1. **Google Search Console** (G1) :
   1. ajouter le site en propriété « Domaine » `everbook-album.com` ;
   2. valider avec l'enregistrement TXT dans ton DNS ;
   3. envoyer `sitemap.xml` ;
   4. dans « Inspection de l'URL », demander l'indexation de `/`, `/fr`, `/faq` et des 3 pages thématiques.
2. **Bing Webmaster Tools** : importer le site depuis Search Console, en un clic. Bing alimente une partie des réponses de ChatGPT et Copilot.
3. **Fiche Google Business Profile** : « Everbook », catégorie photo / impression, zone desservie Liban, site, Instagram, horaires. Ensuite, demander des avis à tes premières clientes.
4. **Liens externes** : bio Instagram et TikTok vers `everbook-album.com`, avec le même nom « Everbook » partout. Annuaires et blogs libanais, partenariats (photographes, wedding planners), presse locale. C'est ce qui fait sortir une marque nouvelle.
5. **Contenus**, que j'intégrerai :
   - le papier (grammage, finition, couverture) ;
   - 300 à 400 mots de plus par page thématique (exemples, petite FAQ par occasion) ;
   - plus tard, une page « album bébé / naissance » et une version arabe.
6. **Deux vérifications rapides** (T5, T8) :
   - ouvrir `https://www.everbook-album.com` : il doit rediriger vers `https://everbook-album.com` ;
   - ouvrir `<adresse du site dev>/robots.txt` : il doit afficher `Disallow: /`.

### Ce que MOI je peux faire dans le code (après ta validation, sur `dev`)

- Les corrections 1, 2 et 4 à 10 ci-dessus. La 9 est en partie liée à tes réponses.
- La correction 3, une fois que tu as tranché la question sur les prix.
- Vérifier chaque correction avec les commandes indiquées, d'abord sur une build locale, puis sur la prod après ton « mets en prod ».

---

## 5. Questions qui bloquent certaines décisions

1. **Prix visibles :** tu avais fait retirer le « à partir de » de l'accueil. Tu préfères :
   - **a)** une question « Combien coûte un album ? » dans la FAQ seulement ;
   - **b)** un bloc de prix sur l'accueil ;
   - **c)** les deux ?
2. **WhatsApp / téléphone :** quel numéro afficher (pied de page, page contact, schema), ou préfères-tu ne pas en mettre ?
3. **Nombre de pages maximum :** le site dit **160**, ton brief dit **200**. Lequel est juste ? Passer à 200 change les prix, l'éditeur et les CGV : ce serait un chantier à part.
4. **Papier et finition :** quels sont les caractéristiques exactes à publier ? Grammage (170 g ?), mat ou brillant, couverture rigide pelliculée…
5. **Réseaux sociaux :** donne-moi les adresses exactes TikTok, Facebook et autres, à ajouter dans `sameAs` et dans le pied de page.
6. **Adresse du site dev :** pour que je vérifie qu'il n'est pas indexable (T8).

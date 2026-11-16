# Fchecker — Architecture

Boîte à outils desktop (Python 3.12+, PySide6) pour contrôler des factures électroniques
Factur-X, CII et UBL dans le cadre de la réforme française.

## Démarrage

```powershell
venv\Scripts\python -m pip install -e .[dev]
venv\Scripts\python main.py [facture.pdf|facture.xml ...]
venv\Scripts\python -m pytest
```

Maintenance des référentiels (développeur) :

```powershell
venv\Scripts\python tools\fetch_rules.py     # télécharge et embarque les packs officiels (SHA-256 vérifiés)
venv\Scripts\python tools\build_catalog.py   # régénère core/catalog/official.yaml (textes officiels)
venv\Scripts\python tools\check_translations.py  # contrôle les traductions maison (en16931_fr.yaml)
```

## Couches

```
ui/        Qt — MVC : vues (widgets) · contrôleurs · modèles Qt (QAbstractTableModel)
plugins/   un sous-paquet par outil : dashboard, validator, mentions, viewer, consistency
core/      Python pur, sans Qt : document, loader, invoice, profiles, schematron, xsd, rules_catalog,
           findings, report, plugin, registry, ids, settings, services/peppol, export
resources/rules/   packs de règles officiels embarqués (hors ligne)
```

Règle absolue : **`core/` n'importe jamais Qt.** Le noyau reste ainsi testable sans interface
et réutilisable pour une CLI ou un traitement par lots.

| Couche | Fichiers clés | Rôle |
|---|---|---|
| Noyau | `core/loader.py` | Détecte le format (Factur-X / CII / UBL), extrait le XML du PDF, lit le XMP (PDF/A, niveau Factur-X) |
| | `core/document.py` | `InvoiceDocument` : XML parsé **une seule fois** (numéros de ligne conservés), parser sans XXE |
| | `core/invoice.py` | Modèle métier normalisé (termes BT) extrait du CII ou de l'UBL ; chaque valeur garde sa ligne XML |
| | `core/profiles.py` | Détection du profil et **chaîne de contrôle** (XSD + schematrons) applicable |
| | `core/schematron.py` | Exécution des XSLT schematron (SaxonC) dans un **processus séparé** (`saxon_worker.py`) ; analyse SVRL |
| | `core/xsd.py`, `core/xpath_locator.py` | Validation XSD (lxml) ; `location` SVRL → n° de ligne |
| | `core/rules_catalog.py` + `core/catalog/` | Traduction de tous les constats (voir « Catalogue ») |
| | `core/services/peppol.py` | Client de l'annuaire Peppol (API REST publique, httpx) et du SMP du participant (peppol.helger.com : SMP, types de documents), avec cache SQLite |
| | `core/export.py` + `core/templates/` | Rapport de contrôle HTML / JSON |
| | `core/ids.py` | Luhn SIREN/SIRET (dérogation La Poste), clé TVA FR, IBAN mod-97 |
| | `core/settings.py` | Réglages applicatifs (JSON, répertoire de configuration utilisateur) |
| Outils | `plugins/validator/checks/` | Sous-contrôles découverts automatiquement : profil, XSD, schematrons, PDF/A, identifiants, annuaire Peppol |
| | `plugins/mentions/` | Check-list des mentions obligatoires (`rules.yaml` + `predicates.py`) |
| | `plugins/consistency/` | Cohérence PDF ↔ XML (texte extrait par pypdf) |
| | `plugins/viewer/` | Rendu lisible (Jinja2 → QtWebEngine), export HTML / PDF |
| UI | `ui/main_window.py` | Assemblage : menus, barre d'outils, raccourcis, glisser-déposer, persistance |
| | `ui/controllers/` | `DocumentController` (ouverture, récents), `RunController` (F5, résultats au fil de l'eau) |
| | `ui/document_tab.py` | Un onglet par facture : vues d'outil créées au premier affichage + volet PDF/XML |
| | `ui/widgets/xml_view.py` | Onglet XML : recherche intégrale surlignée, tout replier / déplier, fil d'Ariane (clic = nœud déplié, reste replié) |
| | `ui/widgets/code_view.py` | Éditeur XML : coloration, repli par élément (gouttière ▸ / ▾), XML compacté réindenté pour l'affichage |
| | `ui/widgets/xml_outline.py` | Découpage du texte XML en éléments (positions, lignes de début et de fin), sans lxml ni Qt : le document est partagé avec les workers |
| | `ui/problems_panel.py` | Panneau « Problèmes » : filtres, fiche détail traduite, navigation XML / PDF |
| | `ui/rule_lookup_dialog.py`, `ui/settings_dialog.py`, `ui/report_export.py` | Catalogue des règles, paramètres, export |

## Réglages

`settings.json` est lu à la racine du projet en développement et, une fois packagé, au même niveau que le .exe
(`core/settings.app_dir`). Le build doit donc le copier à côté de l'exécutable. S'il manque, l'application part
des valeurs par défaut et le recrée à l'enregistrement. Le dossier doit être accessible en écriture : sinon,
Paramètres affiche une erreur et les réglages ne sont pas conservés.

## Référentiels embarqués

`core/referentiels.py` est la liste unique des normes, règles et textes utilisés, avec leur version et leur date
de publication. L'écran Paramètres l'affiche. Les développeurs contrôlent leur fraîcheur avec
`venv\Scripts\python -m fchecker.core.referentiels` (accès réseau, jamais lancé par l'application). Une nouvelle
version CEN, Factur-X ou XSD reste `EN ATTENTE` tant que la FNFE ne l'a pas reprise.

- **Pack FNFE-MPE**, dans `resources/rules/fnfe/` (versions : `core/referentiels.py`). Il contient :
  - les XSLT précompilées EN 16931 CII et UBL ;
  - les règles BR-FR en version standard (flag « fatal ») ;
  - EXTENDED-CTC-FR ;
  - Factur-X (BASIC WL, EN16931, EXTENDED) ;
  - les XSD CII D22B et UBL 2.1.
- **Chaînes de contrôle** (`core/profiles.py`) :
  - Factur-X : XSD du profil, puis schematron du profil (qui inclut EN 16931), puis BR-FR ;
  - CII seul : XSD D22B, puis EN 16931 (ou EXTENDED-CTC-FR), puis BR-FR ;
  - UBL : XSD Invoice ou CreditNote, puis EN 16931 (ou EXTENDED-CTC-FR), puis BR-FR.
- **Profils MINIMUM et BASIC** : non retenus par la réforme, ils déclenchent l'erreur FR-PROFIL-01. BASIC WL est toléré jusqu'au 01/09/2027 (date à confirmer).

## Conformité au socle minimum (dépôt FNFE France_RFE)

- **Pack embarqué** : identique au dépôt `github.com/fnfempe/France_RFE`. Les 38 fichiers
  XSLT/XSD communs ont été comparés après normalisation des fins de ligne.
- **Non-régression** : les 56 factures de test officielles (UC1 à UC13, CII / UBL / Factur-X,
  multi-vendeur, autofacture) sont dans `tests/fixtures/france_rfe/` (Apache-2.0, commit dans
  `SOURCE.txt`). Elles passent tous les contrôles. Seules exceptions : les identifiants fictifs des
  exemples eux-mêmes, figés dans `test_france_rfe_examples.py`.
- **Corpus ezfacture Lab** : `tests/fixtures/lab/` (manifest.yaml + cii/, généré, voir `SOURCE.txt`).
  `test_lab_corpus.py` compare chaque cas au résultat attendu du manifeste : règles `must` levées,
  aucun autre constat plus grave que `max_severity`. Les factures valides de la matrice vérifient
  l'absence de faux positifs. Ne pas modifier ces fichiers à la main : régénérer depuis Lab.
- **Règles de mentions rattachées à des sources publiques** :

  | Règle de l'outil | Source appliquée |
  |---|---|
  | MEN-03 | G6.16, CGI 242 nonies A 7° bis (adresse de livraison) |
  | MEN-04 | G1.43, G1.44, CGI 242 nonies A 11° bis (option débits) |
  | MEN-10 | CGI 293 B, code VATEX-FR-FRANCHISE (franchise en base) |
  | MEN-11 | CGI 242 nonies A 14°, exemples FNFE (autofacture) |
  | MEN-12 | BR-FR-07 (notes ABL / REG) |
  | MEN-13 | BOI-TVA-DECLA-30-20-10-30 (mandataire) |
  | MEN-14 | G1.39, CGI 242 nonies A 10° (date de livraison) |
  | MEN-15 | Code de commerce L441-9 (bon de commande) |

- **Règles non contrôlables** : quand la norme qualifie une règle de « non contrôlable d'un point de
  vue applicatif », l'outil n'émet qu'une **information**, jamais une erreur.

## Catalogue de traduction

Chaque constat est traduit **automatiquement** dans `Tool.publish()` : un outil n'a pas à s'en soucier.

1. `catalog/toolkit.yaml` (manuel, prioritaire) : explications pédagogiques, exemples, fiches des
   règles propres à l'outil (FR-PROFIL, XSD, ID, DIR, PDFA, MEN, COH).
2. `catalog/en16931_fr.yaml` (manuel, EUPL-1.2) : **traduction maison** des 223 règles sémantiques
   EN 16931 et des quelques règles de syntaxe que les motifs ne couvrent pas, avec un glossaire BT/BG.
   Traduite **uniquement depuis l'anglais** des artefacts CEN : la version française de la norme
   et la feuille « Règles de la norme EN16931 » de l'annexe 7 DGFiP qui en dérive
   sont protégées et ne doivent jamais servir de source. `tools/check_translations.py` vérifie la
   couverture, la fraîcheur (`en_sha`) et l'absence de recopie de l'annexe.
3. `catalog/official.yaml` (généré) : message **anglais** de chaque règle EN 16931 (artefacts CEN,
   conservé comme « texte original »), règles de gestion G de la DGFiP, messages BR-FR.
4. Traduction par motifs des messages stéréotypés (CII-SR, UBL-CR, Factur-X, erreurs XSD) et
   rattachement des variantes (`BR-FXEXT-AE-08b` → `BR-AE-08`).

Un test garantit qu'au moins 98 % des règles embarquées sont traduites. La couverture actuelle est d'environ 99 %.

## Ajouter un outil

1. Créer `src/fchecker/plugins/<mon_outil>/__init__.py`. Il ne contient que les métadonnées :
   ```python
   from fchecker.core.plugin import ToolSpec
   SPEC = ToolSpec(id="mon_outil", name="Mon outil", icon="mon_outil", order=60,
                   factory="fchecker.plugins.mon_outil.tool:MonOutil",
                   description="…", runnable=True)
   ```
2. Créer `tool.py` avec une sous-classe de `Tool` :
   - `check(doc, ctx)` : générateur de `Finding`, en Python pur, exécuté hors du thread UI.
   - `create_view(parent, doc)` : renvoie le `QWidget`. Importer Qt **dans** la méthode.
   - `accepts(doc)` : facultatif (ex. `doc.is_pdf`).
   - Si la vue expose `show_report(report)`, elle reçoit les résultats.

   Pour un sous-contrôle du validateur, il suffit d'ajouter un module dans
   `plugins/validator/checks/` qui expose `CHECK = MonCheck()`.
3. Ajouter la fiche de chaque nouvelle règle dans `core/catalog/toolkit.yaml`.
4. Facultatif : ajouter une icône `ui/theme/icons/mon_outil.svg` (24×24, `stroke="currentColor"`).

**Performance** : `__init__.py` doit rester léger. Les imports coûteux (saxonche, QtWebEngine,
pikepdf…) se font dans `tool.py` ou dans les méthodes, jamais au niveau du paquet.

## Bibliothèques natives et threads (impératif)

Chaque règle ci-dessous corrige un crash natif constaté pendant le développement :

- **Workers** : `ThreadPoolExecutor` Python, pas `QThreadPool`. libxml2 n'est pas fiable dans des
  threads créés par Qt.
- **`WorkerSignals`** : il a un parent Qt et n'est détruit que par `deleteLater()` dans le thread UI.
  Connecter les signaux **avant** `start()`.
- **Saxon (SaxonC/GraalVM)** : il tourne dans un **processus séparé** (`core/saxon_worker.py`,
  lancé en `spawn` par `SchematronEngine`), car saxonche garde le GIL pendant la compilation des XSLT
  et gelait l'interface (icônes non dessinées au démarrage). Dialogue par `Pipe` : messages
  `("compile", xslt)`, `("transform", xslt, xml)`, `("stop",)`, réponses `("ok", …)` / `("err", …)`.
  Les requêtes sont sérialisées par un verrou ; en cas de crash ou de délai dépassé, le processus est
  tué et relancé à la requête suivante. Arrêt propre via `SchematronEngine.shutdown()` (`atexit`).
  `main.py` appelle `multiprocessing.freeze_support()` (exécutable PyInstaller).
- **lxml** : les sous-contrôles qui lisent l'arbre XML s'exécutent séquentiellement. Seuls les
  contrôles réseau (`concurrent = True`) tournent en parallèle, sur des données extraites au préalable.
- **pdfium** : une seule copie dans le processus, celle de QtPdf (visionneuse). L'extraction de
  texte utilise pypdf (pur Python). Deux copies de pdfium (pypdfium2 + QtPdf) provoquaient des crashs.
- **QtPdf** : le `QPdfDocument` a pour parent l'onglet (`DocumentTab`), pas la `QPdfView`. Enfant de
  la vue, il était détruit après elle et lui envoyait encore des signaux (crash intermittent à la
  fermeture d'un onglet ou de la fenêtre). `DocumentTab.dispose()`, appelé avant `deleteLater()`,
  détache document et modèle de recherche de la vue puis ferme le document.
- **QtWebEngine** : l'attribut `AA_ShareOpenGLContexts` est positionné avant la création de
  `QApplication`. Le module lui-même n'est importé qu'à l'ouverture de la visionneuse.
- **XML transmis à Saxon** : toujours `InvoiceDocument.xml_text`, c'est-à-dire le document
  re-sérialisé par lxml, jamais les octets bruts. Les exemples officiels commencent par un BOM
  UTF-8, que Saxon refuse. Un schematron qui ne s'exécute pas produit une **erreur** (SCH-ERROR),
  pour qu'une facture non contrôlée ne puisse pas apparaître conforme.

## Feuille de route

1. ✅ Squelette : noyau, registre, interface, thème, tests.
2. ✅ Règles de gestion : packs officiels, profils, mentions, cohérence, catalogue.
3. ✅ Validateur, traduction intégrée, mentions, cohérence PDF ↔ XML, visionneuse, rapport, paramètres.
4. ✅ Packaging Windows : ZIP portable PyInstaller (`packaging/fchecker.spec`, `tools/build_release.py`,
   voir le README). Le spec embarque tout le paquet par `collect_submodules("fchecker")`, car plugins et
   sous-contrôles sont découverts dynamiquement (`pkgutil`) : un nouveau plugin est embarqué sans toucher
   au spec. `settings.json` est écrit à côté de l'exécutable (`core/settings.py`, `app_dir()`), d'où une
   distribution portable plutôt qu'une installation dans Program Files. `Fchecker.exe --self-test <facture>`
   (`fchecker/selftest.py`) contrôle l'exécutable gelé sans interface.
5. À venir : mode lot (dossier de factures), règles B2G (BR-FR-CPRO) dès leur publication par la FNFE.

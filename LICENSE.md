# Licence

Copyright (c) 2026 Siadeo

Distribué sous licence Apache, version 2.0 (la « Licence ») ; vous ne pouvez utiliser ce logiciel que dans le respect des conditions de la Licence. Le texte intégral de la Licence figure dans le fichier [LICENSE](LICENSE) ; il est aussi disponible à l'adresse

   https://www.apache.org/licenses/LICENSE-2.0

Sauf disposition légale applicable ou accord écrit, le logiciel distribué sous la Licence est fourni « EN L'ÉTAT », SANS GARANTIE NI CONDITION D'AUCUNE SORTE, expresse ou implicite. Consultez la Licence pour connaître les termes régissant les autorisations et les limitations qui en découlent.

Les mentions requises par les composants tiers figurent dans le fichier [NOTICE](NOTICE).

## Ce que couvre la Licence

La licence Apache 2.0 couvre le code et les contenus propres au projet : le code source (`src/fchecker/`, hors `resources/rules/`), les outils (`tools/`), les tests (`tests/`, hors `fixtures/france_rfe/`), les catalogues rédigés pour le projet (`src/fchecker/core/catalog/toolkit.yaml`, `plugins/mentions/rules.yaml`), les modèles de rapport et la documentation.

Elle ne s'applique pas aux éléments tiers listés ci-dessous, qui restent régis par leur propre licence, même lorsqu'ils sont distribués avec le projet :

- `src/fchecker/resources/rules/` : référentiels de règles officiels (Apache-2.0 et EUPL-1.2, voir ci-dessous) ;
- `tests/fixtures/france_rfe/` : exemples officiels de factures FNFE-MPE (Apache-2.0) ;
- `src/fchecker/core/catalog/official.yaml` : catalogue généré à partir de textes officiels (artefacts CEN EN 16931, DGFiP, FNFE-MPE) ;
- les bibliothèques installées comme dépendances, qui ne sont pas incluses dans ce dépôt.

## Licences tierces

Ce projet utilise les composants tiers suivants, chacun distribué sous sa propre licence. Tous sont conservés selon les termes de leurs licences respectives.

### Bibliothèques Python

| Composant | Usage | Licence |
|---|---|---|
| [PySide6 / Qt for Python](https://doc.qt.io/qtforpython/) (dont shiboken6, Qt, QtPdf et sa copie de PDFium) | Interface graphique, affichage des PDF | LGPL-3.0 (au choix : GPL-2.0 ou GPL-3.0) ; PDFium : BSD-3-Clause |
| [lxml](https://lxml.de/) (avec libxml2 et libxslt) | Analyse XML, validation XSD | BSD-3-Clause ; libxml2 et libxslt : MIT |
| [SaxonC-HE / saxonche](https://www.saxonica.com/) | Exécution des schematrons XSLT 2.0 | MPL-2.0 |
| [pikepdf](https://github.com/pikepdf/pikepdf) (avec qpdf) | Lecture de la structure PDF/A-3 et des pièces jointes | MPL-2.0 ; qpdf : Apache-2.0 |
| [pypdf](https://github.com/py-pdf/pypdf) | Extraction du texte des PDF | BSD-3-Clause |
| [HTTPX](https://www.python-httpx.org/) (avec httpcore) | Appels aux annuaires Peppol et au SMP | BSD-3-Clause |
| [Jinja2](https://jinja.palletsprojects.com/) (avec MarkupSafe) | Génération du rapport HTML | BSD-3-Clause |
| [PyYAML](https://pyyaml.org/) | Lecture des catalogues de règles | MIT |
| [platformdirs](https://github.com/tox-dev/platformdirs) | Emplacement des réglages et du cache | MIT |

Outils de développement et de test, non distribués avec l'application : pytest (MIT), pytest-qt (MIT), openpyxl (MIT).

### Composants supplémentaires de la release Windows (exécutable)

L'archive `Fchecker-<version>-win64.zip`, construite par PyInstaller (`tools/build_release.py`), contient
en plus les composants suivants. Les bibliothèques Qt y restent des DLL séparées et remplaçables (LGPL-3.0).

| Composant | Usage | Licence |
|---|---|---|
| [Python](https://www.python.org/) (interpréteur et bibliothèque standard, avec OpenSSL, libffi, SQLite, bzip2, xz) | Exécution de l'application | PSF-2.0 ; OpenSSL : Apache-2.0 ; libffi : MIT ; SQLite : domaine public ; bzip2 : BSD ; xz : 0BSD |
| [Qt WebEngine](https://doc.qt.io/qt-6/qtwebengine-licensing.html) (fondé sur Chromium) | Visionneuse, impression des rapports PDF | LGPL-3.0 ; Chromium : BSD-3-Clause et licences tierces listées par Qt |
| [Pillow](https://python-pillow.github.io/) | Dépendance de pikepdf | MIT-CMU |
| [certifi](https://github.com/certifi/python-certifi), anyio, h11, idna, sniffio | Dépendances de HTTPX (certificats, réseau) | MPL-2.0 ; MIT ; MIT ; BSD-3-Clause ; MIT/Apache-2.0 |
| Chargeur [PyInstaller](https://pyinstaller.org/) | Lancement de l'exécutable | GPL-2.0 avec exception autorisant la distribution de l'exécutable sous toute licence |
| Microsoft Visual C++ Runtime | Bibliothèques d'exécution | Licence de redistribution Microsoft |

### Référentiels et données embarqués

| Élément | Emplacement | Licence |
|---|---|---|
| Schematrons FNFE-MPE V1.4.0.04 (règles BR-FR, EXTENDED-CTC-FR, Factur-X 1.09.2), [fnfe-mpe.org](https://fnfe-mpe.org/) | `src/fchecker/resources/rules/fnfe/` | Apache-2.0 |
| Artefacts EN 16931 (schematrons, version 1.3.16) et listes de codes du 15/05/2026, inclus dans le pack FNFE-MPE | `src/fchecker/resources/rules/fnfe/` | EUPL-1.2 |
| Exemples officiels de factures FNFE-MPE ([github.com/fnfempe/France_RFE](https://github.com/fnfempe/France_RFE)), utilisés pour les tests | `tests/fixtures/france_rfe/` | Apache-2.0 (voir `LICENSE` et `SOURCE.txt` du dossier) |
| Messages anglais des règles EN 16931, extraits des artefacts de validation CEN/TC 434 v1.3.16 ([ConnectingEurope/eInvoicing-EN16931](https://github.com/ConnectingEurope/eInvoicing-EN16931)) | `src/fchecker/core/catalog/official.yaml` (généré, entrées marquées `source: Artefacts CEN EN 16931`) | EUPL-1.2 |
| Traduction française des règles EN 16931, réalisée pour Fchecker à partir des messages anglais ci-dessus (sans recours à la version française de la norme) | `src/fchecker/core/catalog/en16931_fr.yaml` | EUPL-1.2 |
| Règles de gestion (G1.xx à G8.xx), reprises sans modification : DGFiP, spécifications externes de la facturation électronique v3.2, annexe 7 « Règles de gestion » (v1.9 du 30/04/2026), [impots.gouv.fr](https://www.impots.gouv.fr/) | `src/fchecker/core/catalog/official.yaml` (généré, entrées marquées `source: DGFiP annexe 7`) | [Licence Ouverte 2.0 (Etalab)](https://www.etalab.gouv.fr/licence-ouverte-open-licence/), selon les [mentions légales d'impots.gouv.fr](https://www.impots.gouv.fr/mentions-legales) ; source et version mentionnées |
| Messages des règles BR-FR, extraits des schematrons FNFE-MPE V1.4.0.04 | `src/fchecker/core/catalog/official.yaml` (généré, entrées marquées `source: Schematron FNFE BR-FR`) | Apache-2.0 |

### Services en ligne interrogés

- Annuaire Peppol (Peppol Directory, [directory.peppol.eu](https://directory.peppol.eu/)), géré par OpenPeppol.
- API REST publique [peppol.helger.com](https://peppol.helger.com/), de Philip Helger : recherche du SMP et des types de documents acceptés.


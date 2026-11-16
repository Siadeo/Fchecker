"""Acceptation de la licence avant toute utilisation, et textes juridiques partagés avec la boîte « À propos »."""
from __future__ import annotations

from datetime import date
from html import escape

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

# À incrémenter si les conditions ci-dessous changent : la fenêtre sera de nouveau présentée.
LICENCE_VERSION = 1
LICENCE_URL = "https://www.apache.org/licenses/LICENSE-2.0"

# Mention exigée par l'accord de licence Commission européenne / CEN du 18/12/2018 pour distribuer une application
# dérivée de l'EN 16931 sans licence supplémentaire. Elle doit rester bien visible : ne pas la retirer.
MENTION_CEN = (
    "Fchecker implémente le modèle sémantique et les deux syntaxes obligatoires de la norme EN 16931. Cette "
    "reproduction est faite avec la permission du CEN et des organismes nationaux de normalisation membres, "
    "titulaires des droits d'auteur. Le CEN et ces organismes n'assument aucune responsabilité quant au contenu "
    "et à la mise en œuvre de cette application et ne donnent aucune garantie, expresse ou implicite. En cas de "
    "doute, seul fait foi le texte officiel mis à disposition par l'organisme national de normalisation."
)

RESPONSABILITE = (
    "Fchecker est une aide au contrôle : il ne garantit ni la validité ou la conformité des factures, ni leur "
    "acceptation par une plateforme agréée ou par l'administration. L'émetteur reste seul responsable de ses "
    "factures. Dans toute la mesure permise par la loi, Siadeo décline toute responsabilité quant à la validité "
    "des factures contrôlées et aux conséquences de leur émission ou de leur rejet."
)
APACHE_AS_IS = (
    "Unless required by applicable law or agreed to in writing, software\n"
    "distributed under the License is distributed on an \"AS IS\" BASIS,\n"
    "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.\n"
    "See the License for the specific language governing permissions and\n"
    "limitations under the License."
)

_CLE_VERSION = "licence/version"
_CLE_DATE = "licence/date"


def licence_acceptee() -> bool:
    return QSettings().value(_CLE_VERSION, 0, type=int) >= LICENCE_VERSION


def enregistrer_acceptation() -> None:
    settings = QSettings()
    settings.setValue(_CLE_VERSION, LICENCE_VERSION)
    settings.setValue(_CLE_DATE, date.today().isoformat())
    settings.sync()


class LicenseDialog(QDialog):
    """Sans choix explicite (croix, Échap), la licence est considérée comme refusée."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Licence de Fchecker")
        self.resize(640, 460)
        layout = QVBoxLayout(self)
        self.texte = QTextBrowser(openExternalLinks=True)
        self.texte.setHtml(
            f"<p>{escape(RESPONSABILITE)}</p>"
            f"<p>{escape(MENTION_CEN)}</p>"
            f"<p><b>Fchecker est distribué sous licence Apache, version 2.0.</b><br>"
            f"<a href='{LICENCE_URL}'>{LICENCE_URL}</a></p>"
            f"<pre>{escape(APACHE_AS_IS)}</pre>")
        layout.addWidget(self.texte, 1)
        self.case = QCheckBox("J'ai lu et j'accepte la licence et ces conditions")
        layout.addWidget(self.case)
        buttons = QDialogButtonBox()
        self.accepter: QPushButton = buttons.addButton("Accepter", QDialogButtonBox.ButtonRole.AcceptRole)
        self.refuser: QPushButton = buttons.addButton("Refuser", QDialogButtonBox.ButtonRole.RejectRole)
        self.accepter.setEnabled(False)
        self.case.toggled.connect(self.accepter.setEnabled)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def demander_licence() -> bool:
    """Vrai si la licence est acceptée, déjà ou à l'instant ; à appeler avant d'afficher l'application."""
    if licence_acceptee():
        return True
    if LicenseDialog().exec() != QDialog.DialogCode.Accepted:
        return False
    enregistrer_acceptation()
    return True

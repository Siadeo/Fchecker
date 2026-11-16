from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor

from fchecker.core.findings import Finding, Severity
from fchecker.ui import theme

FindingRole = Qt.ItemDataRole.UserRole + 1

_SEVERITY_ICON = {Severity.FATAL: "⛔", Severity.ERROR: "✖", Severity.WARNING: "⚠", Severity.INFO: "ℹ"}


class FindingsTableModel(QAbstractTableModel):
    COLUMNS = ("", "Règle", "BT", "Ligne", "Message", "Source")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[Finding] = []

    # --- API -----------------------------------------------------------------
    def set_findings(self, findings: list[Finding]) -> None:
        self.beginResetModel()
        self._rows = list(findings)
        self.endResetModel()

    def append(self, findings: list[Finding]) -> None:
        if not findings:
            return
        start = len(self._rows)
        self.beginInsertRows(QModelIndex(), start, start + len(findings) - 1)
        self._rows.extend(findings)
        self.endInsertRows()

    def clear(self) -> None:
        self.set_findings([])

    def findings(self) -> list[Finding]:
        return list(self._rows)

    def counts(self) -> dict[Severity, int]:
        out = {s: 0 for s in Severity}
        for f in self._rows:
            out[f.severity] += 1
        return out

    # --- Qt ------------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        f = self._rows[index.row()]
        col = index.column()
        if role == FindingRole:
            return f
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                _SEVERITY_ICON[f.severity],
                f.rule_id,
                f.bt or "",
                "" if f.line is None else str(f.line),
                f.display_message,
                f.source.value,
            )[col]
        if role == Qt.ItemDataRole.ToolTipRole:
            if col == 0:
                return f.severity.label
            return f.message if col == 4 else None  # texte d'origine du contrôle
        if role == Qt.ItemDataRole.ForegroundRole and col in (0, 1):
            p = theme.palette()
            return QColor({Severity.FATAL: p.fatal, Severity.ERROR: p.error,
                           Severity.WARNING: p.warning, Severity.INFO: p.info}[f.severity])
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (0, 3):
            return int(Qt.AlignmentFlag.AlignCenter)
        if role == Qt.ItemDataRole.UserRole:  # clé de tri
            return (f.severity, f.rule_id, f.bt or "", f.line or 0, f.display_message, f.source.value)[col]
        return None


class FindingsFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.severities: set[Severity] = set(Severity)
        self.text = ""
        self.setSortRole(Qt.ItemDataRole.UserRole)

    def set_severities(self, severities: set[Severity]) -> None:
        self.beginFilterChange()
        self.severities = severities
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def set_text(self, text: str) -> None:
        self.beginFilterChange()
        self.text = text.casefold().strip()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:
        f: Finding = self.sourceModel().index(row, 0, parent).data(FindingRole)
        if f.severity not in self.severities:
            return False
        if not self.text:
            return True
        hay = " ".join(filter(None, (f.rule_id, f.bt, f.message, f.title, f.source.value))).casefold()
        return self.text in hay

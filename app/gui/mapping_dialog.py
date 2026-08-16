"""Dialog to review and edit column mappings template <-> source."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.core.models import ColumnMapping, MatchSource

MATCH_LABELS = {
    MatchSource.EXACT: "Khớp chính xác",
    MatchSource.FUZZY: "Gợi ý",
    MatchSource.SYNONYM: "Từ điển",
    MatchSource.AI: "AI",
    MatchSource.MANUAL: "Tay",
    MatchSource.UNMAPPED: "Chưa khớp",
}

TYPE_LABELS = {
    "date": "Ngày tháng",
    "number": "Số",
    "int": "Số nguyên",
    "money": "Tiền tệ",
    "email": "Email",
    "phone": "Điện thoại",
    "code": "Mã",
    "text": "Văn bản",
    "unknown": "—",
}


class MappingDialog(QDialog):
    """Show one row per template column with a source-column combo box."""

    def __init__(
        self,
        template_cols: list[str],
        source_cols: list[str],
        mappings: list[ColumnMapping],
        source_types: dict[str, str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Xem & sửa ánh xạ cột")
        self.resize(780, 520)
        self.template_cols = template_cols
        self.source_cols = source_cols
        self.source_types = source_types or {}
        self.result: list[ColumnMapping] = []

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Cột nguồn phát hiện được: " + " | ".join(source_cols)
            )
        )

        self.table = QTableWidget(len(template_cols), 5)
        self.table.setHorizontalHeaderLabels(
            ["Cột trong mẫu", "Cột nguồn (sửa được)", "Nguồn", "Điểm", "Kiểu cột nguồn"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self._combos: dict[int, QComboBox] = {}
        self._type_items: dict[int, QTableWidgetItem] = {}

        for row, tcol in enumerate(template_cols):
            mapping = next(
                (m for m in mappings if m.template_col == tcol),
                ColumnMapping(template_col=tcol, source_col=None),
            )
            self.table.setItem(row, 0, QTableWidgetItem(tcol))
            combo = QComboBox()
            combo.addItem("— Chưa khớp —", None)
            for s in source_cols:
                combo.addItem(s, s)
            if mapping.source_col in source_cols:
                combo.setCurrentIndex(combo.findData(mapping.source_col))
            combo.currentIndexChanged.connect(
                lambda _i, r=row: self._refresh_type_cell(r)
            )
            self.table.setCellWidget(row, 1, combo)
            self._combos[row] = combo
            self.table.setItem(row, 2, QTableWidgetItem(MATCH_LABELS[mapping.match_source]))
            conf = "" if mapping.confidence is None else f"{mapping.confidence:.0f}"
            self.table.setItem(row, 3, QTableWidgetItem(conf))
            type_item = QTableWidgetItem()
            self.table.setItem(row, 4, type_item)
            self._type_items[row] = type_item
            self._refresh_type_cell(row)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        save_btn = QPushButton("Lưu & đóng")
        cancel_btn = QPushButton("Huỷ")
        save_btn.clicked.connect(self._on_save)
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

    def _refresh_type_cell(self, row: int) -> None:
        src = self._combos[row].currentData()
        t = self.source_types.get(src, "unknown") if src else "unknown"
        self._type_items[row].setText(TYPE_LABELS.get(t, t))

    def _on_save(self) -> None:
        result: list[ColumnMapping] = []
        used: set[str] = set()
        for row, tcol in enumerate(self.template_cols):
            src = self._combos[row].currentData()
            if src is not None and src in used:
                QMessageBox.warning(
                    self, "Trùng cột nguồn",
                    f"Cột nguồn '{src}' đang được dùng nhiều lần. Mỗi cột nguồn chỉ được ánh xạ một lần.",
                )
                return
            if src is not None:
                used.add(src)
            result.append(
                ColumnMapping(
                    template_col=tcol,
                    source_col=src,
                    match_source=MatchSource.MANUAL if src else MatchSource.UNMAPPED,
                    confidence=100.0 if src else 0.0,
                )
            )
        self.result = result
        self.accept()

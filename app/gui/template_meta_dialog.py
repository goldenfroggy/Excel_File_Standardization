"""Editor for template column metadata (required, type, default value)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.core.models import Template


class TemplateMetaDialog(QDialog):
    def __init__(self, template: Template, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Thuộc tính cột mẫu — {template.path.name}")
        self.resize(640, 480)
        self.template = template

        layout = QVBoxLayout(self)
        self.table = QTableWidget(len(template.columns), 4)
        self.table.setHorizontalHeaderLabels(
            ["Cột", "Bắt buộc", "Kiểu dữ liệu", "Giá trị mặc định"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self._required: dict[int, QCheckBox] = {}
        self._types: dict[int, QComboBox] = {}

        for r, col in enumerate(template.columns):
            self.table.setItem(r, 0, QTableWidgetItem(col.name))
            cb = QCheckBox()
            cb.setChecked(col.required)
            self.table.setCellWidget(r, 1, cb)
            self._required[r] = cb
            combo = QComboBox()
            for label, val in [
                ("Văn bản", "text"),
                ("Ngày tháng", "date"),
                ("Số", "number"),
                ("Số nguyên", "int"),
                ("Tiền tệ", "money"),
            ]:
                combo.addItem(label, val)
            if col.data_type:
                idx = combo.findData(col.data_type)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            self.table.setCellWidget(r, 2, combo)
            self._types[r] = combo
            self.table.setItem(r, 3, QTableWidgetItem(_val(col.default_value)))
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        save_btn = QPushButton("Lưu")
        cancel_btn = QPushButton("Huỷ")
        save_btn.clicked.connect(self._on_save)
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

    def _on_save(self) -> None:
        for r, col in enumerate(self.template.columns):
            col.required = self._required[r].isChecked()
            col.data_type = self._types[r].currentData()
            item = self.table.item(r, 3)
            col.default_value = _parse_val(item.text() if item else "")
        from app.core.template import save_meta

        save_meta(self.template)
        self.accept()


def _val(v) -> str:
    return "" if v is None else str(v)


def _parse_val(text: str):
    text = text.strip()
    if not text:
        return None
    if text in {"True", "true"}:
        return True
    if text in {"False", "false"}:
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text

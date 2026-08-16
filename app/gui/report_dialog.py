"""Per-file issue report dialog with CSV export."""

from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.core.models import FileReport


class ReportDialog(QDialog):
    def __init__(self, report: FileReport, parent=None) -> None:
        super().__init__(parent)
        self.report = report
        self.setWindowTitle(f"Báo cáo: {Path(report.source_path).name}")
        self.resize(800, 480)

        layout = QVBoxLayout(self)
        header = (
            f"{Path(report.source_path).name} — trạng thái: {report.status}, "
            f"{report.row_count} dòng, {report.mapped_columns} cột khớp, "
            f"{report.error_count} lỗi, {report.warning_count} cảnh báo"
        )
        layout.addWidget(QLabel(header))

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Dòng", "Cột", "Mức độ", "Loại", "Chi tiết"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        for issue in report.issues:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(str(issue.row or "")))
            self.table.setItem(r, 1, QTableWidgetItem(issue.column))
            self.table.setItem(r, 2, QTableWidgetItem(issue.severity.value))
            self.table.setItem(r, 3, QTableWidgetItem(issue.type.value))
            self.table.setItem(r, 4, QTableWidgetItem(issue.message))

        if report.error_message:
            layout.addWidget(QLabel(f"Lỗi xử lý: {report.error_message}"))

        buttons = QHBoxLayout()
        export_btn = QPushButton("Xuất báo cáo CSV…")
        close_btn = QPushButton("Đóng")
        export_btn.clicked.connect(self._export_csv)
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(export_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    def _export_csv(self) -> None:
        default = self.report.source_path.with_suffix(".report.csv").name
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu báo cáo", default, "CSV (*.csv)"
        )
        if not path:
            return
        try:
            with Path(path).open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Dòng", "Cột", "Mức độ", "Loại", "Chi tiết"])
                for issue in self.report.issues:
                    writer.writerow(
                        [issue.row, issue.column, issue.severity.value,
                         issue.type.value, issue.message]
                    )
            QMessageBox.information(self, "Đã lưu", f"Báo cáo đã lưu tại:\n{path}")
        except OSError as exc:
            QMessageBox.critical(self, "Lỗi", f"Không lưu được báo cáo:\n{exc}")

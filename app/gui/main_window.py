"""Main window: wizard-like flow for batch standardization."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.config import AppSettings, ROOT
from app.core.matcher import match_columns
from app.core.models import FileReport
from app.core.presets import PresetStore
from app.core.processor import build_mappings, process_batch
from app.core.reader import (
    _read_head,
    detect_header_row,
    list_sheets,
    read_frame,
    read_frame_head,
    sample_values,
)
from app.core.synonyms import SynonymStore
from app.core.type_inference import infer_column_type
from app.core.template import load_template
from app.gui.mapping_dialog import MappingDialog
from app.gui.report_dialog import ReportDialog
from app.gui.settings_dialog import SettingsDialog
from app.gui.template_meta_dialog import TemplateMetaDialog

STATUS_LABELS = {"ok": "OK", "partial": "Có lỗi", "failed": "Thất bại"}


class BatchWorker(QThread):
    report_done = Signal(object)
    finished_batch = Signal(object)

    def __init__(
        self, files, template, settings, output_dir, sheet, skip, override
    ) -> None:
        super().__init__()
        self._files = files
        self._template = template
        self._settings = settings
        self._output_dir = output_dir
        self._sheet = sheet
        self._skip = skip
        self._override = override
        self._cancel = threading.Event()

    def run(self) -> None:
        batch = process_batch(
            self._files,
            self._template,
            self._settings,
            self._output_dir,
            sheet_name=self._sheet,
            skip_rows=self._skip,
            progress=self.report_done.emit,
            cancel_event=self._cancel,
            mappings_override=self._override,
        )
        self.finished_batch.emit(batch)

    def cancel(self) -> None:
        self._cancel.set()


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Chuẩn hoá File Excel")
        self.resize(980, 720)
        self.settings = AppSettings.load()
        self.template_dir = Path(self.settings.templates_dir)
        self.template_dir.mkdir(parents=True, exist_ok=True)
        self.current_template = None
        self.override = None  # list[ColumnMapping] | None
        self.override_signature = None
        self.worker = None
        self.reports: dict[Path, FileReport] = {}
        self.presets = PresetStore()

        root = QVBoxLayout(self)
        root.addLayout(self._build_template_row())
        root.addLayout(self._build_input_row())
        root.addLayout(self._build_options_row())
        root.addLayout(self._build_run_row())
        self._refresh_templates()
        self._sync_template_ui()

    # ---------- UI construction ----------

    def _build_template_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        box = QGroupBox("1. Chọn mẫu (template)")
        inner = QHBoxLayout(box)
        self.template_combo = QComboBox()
        self.template_combo.currentIndexChanged.connect(self._on_template_changed)
        import_btn = QPushButton("Thêm mẫu mới…")
        import_btn.clicked.connect(self._import_template)
        meta_btn = QPushButton("Thuộc tính cột mẫu…")
        meta_btn.clicked.connect(self._edit_meta)
        self.template_preview = QLabel()
        self.template_preview.setWordWrap(True)
        inner.addWidget(self.template_combo, 3)
        inner.addWidget(import_btn)
        inner.addWidget(meta_btn)
        inner.addWidget(self.template_preview, 2)
        row.addWidget(box, 1)
        return row

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        box = QGroupBox("2. File nguồn (chọn nhiều)")
        inner = QVBoxLayout(box)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        btns = QHBoxLayout()
        add_files = QPushButton("Thêm file…")
        add_folder = QPushButton("Thêm thư mục…")
        remove_btn = QPushButton("Bỏ chọn")
        add_files.clicked.connect(self._add_files)
        add_folder.clicked.connect(self._add_folder)
        remove_btn.clicked.connect(self._remove_selected)
        btns.addWidget(add_files)
        btns.addWidget(add_folder)
        btns.addWidget(remove_btn)
        btns.addStretch()
        btns.addWidget(QLabel("Sheet:"))
        self.sheet_combo = QComboBox()
        self.sheet_combo.addItem("(Sheet đầu tiên)", None)
        btns.addWidget(self.sheet_combo)
        btns.addWidget(QLabel("Bỏ qua dòng đầu:"))
        self.skip_spin = QSpinBox()
        self.skip_spin.setRange(0, 100)
        self.skip_spin.setValue(self.settings.default_skip_rows)
        btns.addWidget(self.skip_spin)
        inner.addWidget(self.file_list)
        inner.addLayout(btns)
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Thư mục kết quả:"))
        self.output_edit = QLineEdit(self.settings.last_output_dir)
        browse_btn = QPushButton("…")
        browse_btn.clicked.connect(self._browse_output)
        out_row.addWidget(self.output_edit, 1)
        out_row.addWidget(browse_btn)
        inner.addLayout(out_row)
        self.header_info = QLabel("")
        self.header_info.setWordWrap(True)
        self.header_info.setStyleSheet("color: #555;")
        inner.addWidget(self.header_info)
        row.addWidget(box, 1)
        return row

    def _build_options_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        box = QGroupBox("3. Chế độ & ánh xạ")
        inner = QHBoxLayout(box)
        self.ai_check = QCheckBox("Dùng AI cho cột chưa khớp")
        self.ai_check.setChecked(self.settings.ai.enabled)
        self.ai_check.toggled.connect(self._on_ai_toggled)
        settings_btn = QPushButton("Cài đặt…")
        settings_btn.clicked.connect(self._open_settings)
        map_btn = QPushButton("Xem & sửa ánh xạ…")
        map_btn.clicked.connect(self._review_mapping)
        clear_map_btn = QPushButton("Bỏ ánh xạ tay")
        clear_map_btn.clicked.connect(self._clear_override)
        self.threshold_label = QLabel()
        inner.addWidget(self.ai_check)
        inner.addWidget(settings_btn)
        inner.addWidget(map_btn)
        inner.addWidget(clear_map_btn)
        inner.addWidget(self.threshold_label, 1)
        row.addWidget(box, 1)
        return row

    def _build_run_row(self) -> QVBoxLayout:
        col = QVBoxLayout()
        box = QGroupBox("4. Chạy")
        inner = QVBoxLayout(box)
        run_row = QHBoxLayout()
        self.run_btn = QPushButton("Chuẩn hoá tất cả")
        self.run_btn.clicked.connect(self._run_batch)
        self.cancel_btn = QPushButton("Dừng")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_batch)
        self.progress = QProgressBar()
        run_row.addWidget(self.run_btn)
        run_row.addWidget(self.cancel_btn)
        run_row.addWidget(self.progress, 1)
        inner.addLayout(run_row)

        self.result_table = QTableWidget(0, 5)
        self.result_table.setHorizontalHeaderLabels(
            ["File", "Trạng thái", "Dòng", "Lỗi", "File kết quả"]
        )
        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.result_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.doubleClicked.connect(self._show_report)
        inner.addWidget(self.result_table)
        col.addWidget(box, 1)
        return col

    # ---------- template handling ----------

    def _refresh_templates(self) -> None:
        self.template_combo.clear()
        for path in sorted(self.template_dir.rglob("*.xlsx")) + sorted(
            self.template_dir.rglob("*.xls")
        ) + sorted(self.template_dir.rglob("*.csv")):
            self.template_combo.addItem(path.name, str(path))
        if self.settings.last_template:
            idx = self.template_combo.findData(self.settings.last_template)
            if idx >= 0:
                self.template_combo.setCurrentIndex(idx)

    def _on_template_changed(self) -> None:
        self.current_template = None
        self.override = None
        data = self.template_combo.currentData()
        if not data:
            return
        try:
            self.current_template = load_template(
                Path(data), sheet_name=self.settings.default_sheet,
                skip_rows=self.settings.default_skip_rows,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi đọc mẫu", str(exc))
            return
        self._sync_template_ui()

    def _sync_template_ui(self) -> None:
        if self.current_template:
            cols = ", ".join(self.current_template.column_names)
            self.template_preview.setText(f"Cột mẫu: {cols}")
        else:
            self.template_preview.setText("Chưa chọn mẫu")

    def _import_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file mẫu",
            str(self.template_dir), "Excel/CSV (*.xlsx *.xls *.csv)",
        )
        if not path:
            return
        src = Path(path)
        dest = self.template_dir / src.name
        if dest.exists():
            QMessageBox.information(
                self, "Trùng tên", f"Đã có mẫu tên {src.name} trong thư viện, ghi đè."
            )
        try:
            dest.write_bytes(src.read_bytes())
        except OSError as exc:
            QMessageBox.critical(self, "Lỗi", str(exc))
            return
        self._refresh_templates()
        idx = self.template_combo.findData(str(dest))
        if idx >= 0:
            self.template_combo.setCurrentIndex(idx)

    def _edit_meta(self) -> None:
        if not self.current_template:
            QMessageBox.information(self, "Chú ý", "Vui lòng chọn mẫu trước.")
            return
        dlg = TemplateMetaDialog(self.current_template, self)
        if dlg.exec():
            self._sync_template_ui()

    # ---------- input files ----------

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Chọn file nguồn", "", "Excel/CSV (*.xlsx *.xls *.csv)"
        )
        self._append_files(paths)

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục")
        if not folder:
            return
        paths = []
        for pattern in ("*.xlsx", "*.xls", "*.csv"):
            paths.extend(str(p) for p in Path(folder).glob(pattern))
        self._append_files(paths)

    def _append_files(self, paths: list[str]) -> None:
        existing = {self.file_list.item(i).text() for i in range(self.file_list.count())}
        for p in paths:
            if p not in existing:
                self.file_list.addItem(p)
        self._refresh_sheets()
        self._refresh_header_info()

    def _refresh_header_info(self) -> None:
        if self.file_list.count() == 0:
            self.header_info.setText("")
            return
        path = Path(self.file_list.item(0).text())
        try:
            sheet = self.sheet_combo.currentData()
            raw = read_frame(path, sheet_name=sheet)
            idx = detect_header_row(_read_head(path, sheet))
            preview = [str(v) for v in list(raw.iloc[0].tolist())[:6]]
            self.header_info.setText(
                f"Phát hiện header dòng {idx + 1}; dữ liệu đầu: "
                + " | ".join(preview)
            )
        except Exception:
            self.header_info.setText("Không đọc được header tự động.")

    def _remove_selected(self) -> None:
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))
        self._refresh_sheets()
        self._refresh_header_info()

    def _refresh_sheets(self) -> None:
        self.sheet_combo.clear()
        self.sheet_combo.addItem("(Sheet đầu tiên)", None)
        if self.file_list.count() == 0:
            return
        first = Path(self.file_list.item(0).text())
        try:
            for s in list_sheets(first):
                self.sheet_combo.addItem(s, s)
        except Exception:
            pass

    def _browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục kết quả", self.output_edit.text()
        )
        if folder:
            self.output_edit.setText(folder)

    # ---------- options ----------

    def _on_ai_toggled(self, checked: bool) -> None:
        self.settings.ai.enabled = checked

    def _open_settings(self) -> None:
        SettingsDialog(self.settings, self).exec()
        self.ai_check.setChecked(self.settings.ai.enabled)
        self.threshold_label.setText(f"Ngưỡng khớp: {self.settings.fuzzy_threshold:.0f}%")
        self.settings.save()

    def _clear_override(self) -> None:
        self.override = None
        self.override_signature = None
        self._sync_template_ui()
        QMessageBox.information(self, "Đã bỏ", "Đã bỏ ánh xạ tay, sẽ tự khớp lại.")

    # ---------- mapping review ----------

    def _first_source(self) -> tuple[Path, list[str], dict[str, list]] | None:
        if self.file_list.count() == 0:
            return None
        path = Path(self.file_list.item(0).text())
        sheet = self.sheet_combo.currentData()
        try:
            header = read_frame_head(
                path, sheet_name=sheet, skip_rows=self.skip_spin.value(),
            )
            samples = sample_values(
                path, sheet_name=sheet, skip_rows=self.skip_spin.value(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi đọc file", str(exc))
            return None
        return path, header, samples

    def _review_mapping(self) -> None:
        if not self.current_template:
            QMessageBox.information(self, "Chú ý", "Vui lòng chọn mẫu trước.")
            return
        first = self._first_source()
        if first is None:
            QMessageBox.information(self, "Chú ý", "Vui lòng thêm ít nhất 1 file nguồn.")
            return
        _, header, samples = first
        sig = tuple(header)
        synonyms = SynonymStore()
        preset = self.presets.get(str(self.current_template.path), header)
        if preset is not None:
            mappings = preset
            source_note = " (đã tải từ ánh xạ đã lưu)"
        else:
            mappings = build_mappings(
                self.current_template, header, self.settings,
                source_samples=samples, synonyms=synonyms,
            )
            source_note = " (gợi ý tự động)"
        source_types = {
            scol: infer_column_type(vals) for scol, vals in samples.items()
        }
        dlg = MappingDialog(
            self.current_template.column_names, header, mappings,
            source_types=source_types, parent=self,
        )
        dlg.setWindowTitle(f"Xem & sửa ánh xạ{source_note}")
        if dlg.exec():
            self.override = dlg.result
            self.override_signature = sig
            self.presets.put(str(self.current_template.path), header, dlg.result)
            self._learn_synonyms(mappings, dlg.result, synonyms)
            self.template_preview.setText(
                "Đã lưu ánh xạ tay cho mẫu hiện tại."
            )

    def _learn_synonyms(
        self, original: list, chosen: list, synonyms: SynonymStore
    ) -> None:
        """Remember only pairs the user actually changed, so later runs match
        the same abbreviations automatically."""
        orig = {m.template_col: m.source_col for m in original}
        for m in chosen:
            if m.source_col and m.source_col != orig.get(m.template_col):
                synonyms.add(m.template_col, m.source_col)

    # ---------- batch run ----------

    def _run_batch(self) -> None:
        if not self.current_template:
            QMessageBox.information(self, "Chú ý", "Chọn mẫu trước.")
            return
        if self.file_list.count() == 0:
            QMessageBox.information(self, "Chú ý", "Thêm ít nhất 1 file nguồn.")
            return
        out_dir = Path(self.output_edit.text().strip() or ROOT / "output")
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Lỗi", f"Không tạo được thư mục kết quả:\n{exc}")
            return

        files = [Path(self.file_list.item(i).text()) for i in range(self.file_list.count())]
        override = self.override if self.override_signature else None

        self.settings.last_template = str(self.current_template.path)
        self.settings.last_output_dir = str(out_dir)
        self.settings.save()

        self.reports = {}
        self.result_table.setRowCount(0)
        self.progress.setRange(0, len(files))
        self.progress.setValue(0)
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        self.worker = BatchWorker(
            files, self.current_template, self.settings, out_dir,
            self.sheet_combo.currentData(), self.skip_spin.value(), override,
        )
        self.worker.report_done.connect(self._on_report)
        self.worker.finished_batch.connect(self._on_finished)
        self.worker.start()

    def _on_report(self, report: FileReport) -> None:
        self.progress.setValue(self.progress.value() + 1)
        r = self.result_table.rowCount()
        self.result_table.insertRow(r)
        self.result_table.setItem(r, 0, QTableWidgetItem(report.source_path.name))
        self.result_table.setItem(r, 1, QTableWidgetItem(STATUS_LABELS.get(report.status, report.status)))
        self.result_table.setItem(r, 2, QTableWidgetItem(str(report.row_count)))
        self.result_table.setItem(r, 3, QTableWidgetItem(str(report.error_count)))
        self.result_table.setItem(
            r, 4,
            QTableWidgetItem(str(report.output_path) if report.output_path else report.error_message or ""),
        )
        self.reports[report.source_path] = report

    def _on_finished(self, batch) -> None:
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        QMessageBox.information(
            self, "Hoàn tất",
            f"Xong: {batch.ok_count} file OK, {batch.failed_count} file thất bại.",
        )

    def _cancel_batch(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)

    def _show_report(self, index) -> None:
        row = index.row()
        if row >= len(self.reports):
            return
        report = list(self.reports.values())[row]
        ReportDialog(report, self).exec()

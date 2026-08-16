"""Application settings dialog (AI + cleaning rules)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.core.config import AppSettings


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cài đặt")
        self.resize(520, 460)
        self.settings = settings

        layout = QVBoxLayout(self)

        ai_box = QGroupBox("Chế độ AI (gợi ý ánh xạ cột)")
        ai_form = QFormLayout(ai_box)
        self.ai_enabled = QCheckBox("Bật AI")
        self.ai_enabled.setChecked(settings.ai.enabled)
        self.ai_aggressive = QCheckBox("AI mạnh hơn (tốn thêm token)")
        self.ai_aggressive.setChecked(settings.ai.aggressive)
        self.ai_aggressive.setToolTip(
            "Gửi cả các cột khớp mờ điểm thấp cho AI xác nhận lại. "
            "Mặc định AI chỉ xử lý cột chưa khớp để tiết kiệm token."
        )
        self.ai_key = QLineEdit(settings.ai.api_key)
        self.ai_key.setEchoMode(QLineEdit.Password)
        self.ai_url = QLineEdit(settings.ai.base_url)
        self.ai_model = QLineEdit(settings.ai.model)
        self.ai_max_tokens = QSpinBox()
        self.ai_max_tokens.setRange(50, 2000)
        self.ai_max_tokens.setValue(settings.ai.max_tokens)
        ai_form.addRow(self.ai_enabled)
        ai_form.addRow("", self.ai_aggressive)
        ai_form.addRow("API key", self.ai_key)
        ai_form.addRow("Base URL", self.ai_url)
        ai_form.addRow("Model (ưu tiên rẻ/nhanh)", self.ai_model)
        ai_form.addRow("Max tokens", self.ai_max_tokens)
        ai_form.addRow(
            "",
            QLabel(
                "AI chỉ xử lý cột chưa khớp, kết quả được cache trên đĩa "
                "nên không tốn token khi chạy lại."
            ),
        )
        layout.addWidget(ai_box)

        fuzzy_box = QGroupBox("Khớp cột thường")
        fuzzy_form = QFormLayout(fuzzy_box)
        self.fuzzy_threshold = QDoubleSpinBox()
        self.fuzzy_threshold.setRange(0, 100)
        self.fuzzy_threshold.setDecimals(1)
        self.fuzzy_threshold.setValue(settings.fuzzy_threshold)
        self.fuzzy_threshold.setSuffix(" %")
        fuzzy_form.addRow("Ngưỡng tương đồng (cao → ít AI hơn)", self.fuzzy_threshold)
        layout.addWidget(fuzzy_box)

        clean_box = QGroupBox("Làm sạch dữ liệu")
        clean_form = QFormLayout(clean_box)
        self.c_trim = QCheckBox("Cắt khoảng trắng")
        self.c_trim.setChecked(settings.clean.trim)
        self.c_unicode = QCheckBox("Chuẩn hoá Unicode")
        self.c_unicode.setChecked(settings.clean.normalize_unicode)
        self.c_currency = QCheckBox("Bỏ ký hiệu tiền tệ / dấu phân tách")
        self.c_currency.setChecked(settings.clean.strip_currency)
        self.c_defaults = QCheckBox("Điền giá trị mặc định cho cột bắt buộc")
        self.c_defaults.setChecked(settings.clean.fill_defaults)
        self.c_case = QComboBox()
        self.c_case.addItem("Giữ nguyên", "none")
        self.c_case.addItem("Chữ hoa", "upper")
        self.c_case.addItem("Chữ thường", "lower")
        self.c_case.addItem("Viết hoa đầu từ", "title")
        idx = self.c_case.findData(settings.clean.case)
        self.c_case.setCurrentIndex(max(idx, 0))
        self.c_date = QLineEdit(settings.clean.output_date_format)
        clean_form.addRow(self.c_trim)
        clean_form.addRow(self.c_unicode)
        clean_form.addRow(self.c_currency)
        clean_form.addRow(self.c_defaults)
        clean_form.addRow("Kiểu chữ", self.c_case)
        clean_form.addRow("Định dạng ngày xuất ra", self.c_date)
        layout.addWidget(clean_box)

        save_btn = QPushButton("Lưu")
        save_btn.clicked.connect(self._on_save)
        layout.addWidget(save_btn)

    def _on_save(self) -> None:
        self.settings.ai.enabled = self.ai_enabled.isChecked()
        self.settings.ai.aggressive = self.ai_aggressive.isChecked()
        self.settings.ai.api_key = self.ai_key.text().strip()
        self.settings.ai.base_url = self.ai_url.text().strip()
        self.settings.ai.model = self.ai_model.text().strip()
        self.settings.ai.max_tokens = self.ai_max_tokens.value()
        self.settings.fuzzy_threshold = self.fuzzy_threshold.value()
        self.settings.clean.trim = self.c_trim.isChecked()
        self.settings.clean.normalize_unicode = self.c_unicode.isChecked()
        self.settings.clean.strip_currency = self.c_currency.isChecked()
        self.settings.clean.fill_defaults = self.c_defaults.isChecked()
        self.settings.clean.case = self.c_case.currentData()
        self.settings.clean.output_date_format = self.c_date.text().strip() or "%d/%m/%Y"
        self.settings.save()
        self.accept()

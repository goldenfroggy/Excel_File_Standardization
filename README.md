# Chuẩn hoá File Excel theo mẫu

Phần mềm desktop (PySide6) giúp **chuẩn hoá nhiều file Excel/CSV cùng lúc** theo một **file mẫu cố định** do người dùng chọn: tự ánh xạ cột, sắp xếp theo thứ tự mẫu, làm sạch dữ liệu (ngày tháng, số, chữ), điền giá trị mặc định và xuất báo cáo lỗi chi tiết.

## Tính năng

- Đọc **XLSX / XLS / CSV**, xử lý **nhiều file song song**.
- **Tự dò hàng tiêu đề**: nhận diện dòng tên cột thật giữa các dòng banner/tiêu đề/ô gộp (không cần chỉnh tay), kèm **tự chọn sheet dữ liệu** khi file có nhiều sheet.
- **Nhận diện bảng chuyển vị** (tên cột nằm theo hàng, mỗi cột là một bản ghi) — tự đảo về đúng chuẩn.
- Ánh xạ cột theo mẫu qua **các lớp tiết kiệm token**:
  1. Khớp chính xác + khớp từ (token) + **khớp kiểu dữ liệu** (ngày/số/tiền/…) tại máy — 0 token,
  2. **Từ điển đồng nghĩa tự học**: khi bạn sửa ánh xạ tay một lần, cặp tên đó được nhớ lại (`config/synonyms.json`) để các lần sau tự khớp, kể cả tên viết tắt như `MSNV`, `HoTen`, `DOB`,
  3. **AI** chỉ nhận các cột chưa khớp (kèm kiểu dữ liệu để gợi ý đúng hơn) — kết quả **cache trên đĩa** nên lô trùng cấu trúc tốn **0 token**.
- Xem & sửa ánh xạ tay (hiện kèm điểm tin cậy + kiểu cột phát hiện), lưu làm preset để dùng lại.
- Làm sạch dữ liệu: chuẩn hoá Unicode, cắt khoảng trắng, chữ hoa/thường, đổi định dạng ngày tháng, bỏ ký hiệu tiền tệ/phân tách số.
- Khai báo cột bắt buộc, kiểu dữ liệu, giá trị mặc định cho mẫu.
- Báo cáo lỗi/sai định dạng từng dòng, xuất ra CSV.

## Cài đặt & chạy

Yêu cầu: Python 3.10+ (khuyến nghị 3.12+).

**Linux / WSL:**

```bash
./run.sh
```

**Windows:**

```
run.bat
```

Lần đầu `run.sh` / `run.bat` tự tạo môi trường ảo và cài dependencies từ `requirements.txt`. Hai môi trường tách riêng: WSL dùng `.venv`, Windows dùng `.venv-win` (không tương thích chéo nên đừng trộn).

Chạy thủ công:

```bash
# Linux / WSL
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

```bat
rem Windows
py -3 -m venv .venv-win
.venv-win\Scripts\python -m pip install -r requirements.txt
.venv-win\Scripts\python main.py
```

> Ghi chú WSL: GUI hiển thị qua WSLg; nếu không thấy cửa sổ, kiểm tra `echo $DISPLAY`.
> Windows: cần Python 3.10+ (có tích hợp "py launcher"). Khi chạy trên Windows, AI base URL mặc định tự dùng `http://127.0.0.1:20128/v1` (chỉnh được trong *Cài đặt*).

## Cách dùng

1. **Chọn mẫu**: nút *Thêm mẫu mới…* để đưa file mẫu vào thư mục `templates/` (dòng đầu là tên cột chuẩn). Nút *Thuộc tính cột mẫu…* để đánh dấu cột bắt buộc, kiểu dữ liệu (text/date/number/money/int) và giá trị mặc định — lưu kèm file mẫu.
2. **Thêm file nguồn**: chọn nhiều file hoặc cả thư mục. App **tự dò hàng tiêu đề** (kể cả khi có banner/tiêu đề phía trên) và **tự chọn sheet dữ liệu**; bạn chỉ cần chỉnh nếu muốn chọn sheet khác hoặc bỏ qua N dòng đầu.
3. **Ánh xạ cột**: nút *Xem & sửa ánh xạ…* để duyệt/điều chỉnh ánh xạ tự động (hiện kiểu cột + điểm tin cậy). **Sửa tay một lần là học được**: từ lần sau các tên viết tắt như `MSNV`, `DOB` sẽ tự khớp. *Cài đặt…* để cấu hình API AI (chế độ "AI mạnh hơn" nếu muốn tốn thêm token để gợi ý chính xác hơn).
4. **Chạy**: *Chuẩn hoá tất cả* — kết quả ghi vào thư mục đích với hậu tố `_standardized.xlsx`. Nhấn đúp vào dòng kết quả để xem báo cáo lỗi chi tiết.

## Cấu hình AI

Trong *Cài đặt* → *Chế độ AI*, nhập:

- **Base URL** và **API key** (mặc định trỏ tới endpoint OpenAI-compatible; ví dụ OmniRoute).
- **Model**: ưu tiên chọn model rẻ/nhanh (mặc định `auto/fast`), không cần dùng model lớn vì tác vụ chỉ là ánh xạ tên cột.
- **Max tokens**: mặc định 200 — chỉ gửi danh sách cột, không bao giờ gửi nội dung dữ liệu lên AI.

AI key lưu tại `config/settings.json` (đã có trong `.gitignore`, **không** commit lên git). Cache kết quả ở `config/ai_cache.json`.

## Cấu trúc

```
app/
├── main.py                 # điểm vào
├── core/                   # engine không phụ thuộc GUI
│   ├── models.py           # Template, ColumnMapping, FileReport, Issue
│   ├── template.py         # đọc mẫu + metadata sidecar (.template.json)
│   ├── reader.py           # đọc xlsx/xls/csv, phát hiện header
│   ├── matcher.py          # khớp chính xác + fuzzy (rapidfuzz)
│   ├── ai_matcher.py       # AI gợi ý + cache tiết kiệm token
│   ├── cleaner.py          # làm sạch dữ liệu
│   ├── processor.py        # engine hàng loạt + báo cáo
│   ├── presets.py          # lưu preset ánh xạ
│   └── config.py           # cài đặt (config/settings.json)
└── gui/                    # giao diện PySide6
    ├── main_window.py      # luồng chính
    ├── mapping_dialog.py   # sửa ánh xạ cột
    ├── report_dialog.py    # báo cáo lỗi
    ├── settings_dialog.py  # cấu hình AI + làm sạch
    └── template_meta_dialog.py
templates/                  # thư mục chứa file mẫu
config/                     # settings.json, ai_cache.json, presets.json (gitignored)
tests/                      # pytest
```

## Kiểm thử

```bash
.venv/bin/python -m pytest -q
```

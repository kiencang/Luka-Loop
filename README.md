# luka-loop

Quy trình AI Agent tự động dịch tài liệu PDF (bao gồm cả PDF scan và PDF học thuật nhiều hình minh họa, bảng biểu, công thức) sang bản **HTML tiếng Việt** (*self-contained* về hình ảnh và giao diện đọc) và **PDF** song song trên Windows, không yêu cầu cài đặt Python hệ thống.

## Yêu cầu hệ thống
- **Hệ điều hành:** Windows 10 hoặc Windows 11 **64-bit (x64)** *(bộ công cụ `extract_assets.exe` hiện biên dịch ở kiến trúc x64, chưa hỗ trợ Windows 32-bit)*.
- **PowerShell:** Windows PowerShell 5.1 (có sẵn mặc định trên Windows 10/11).
- **Trình duyệt (tùy chọn để tự động xuất PDF):** Microsoft Edge (ưu tiên) hoặc Google Chrome. Nếu không có, quy trình vẫn xuất hoàn chỉnh tệp `*_vi.html`.

## Cấu trúc dự án
- [`AGENTS.md`](./AGENTS.md) — Quy tắc điều phối dành cho AI Agent trong workspace.
- [`.agents/skills/pdf-to-html-vi/`](./.agents/skills/pdf-to-html-vi/) — Skill `pdf-to-html-vi` gồm quy trình 4 bước ([`SKILL.md`](./.agents/skills/pdf-to-html-vi/SKILL.md)) và bộ chuẩn dịch thuật học thuật / CSS ([`si_academic_html.md`](./.agents/skills/pdf-to-html-vi/si_academic_html.md)).
- [`tools/`](./tools/) — Bộ công cụ PowerShell & portable:
  - [`extract_pdf_assets.ps1`](./tools/extract_pdf_assets.ps1) gọi [`extract_assets/extract_assets.exe`](./tools/extract_assets/extract_assets.exe) để tự động tách ảnh/sơ đồ và xuất `manifest.json`.
  - [`pdf_fallback_tools.ps1`](./tools/pdf_fallback_tools.ps1) render trang PDF scan qua WinRT `Windows.Data.Pdf` và cắt khung ảnh theo JSON.
  - [`html_packager.ps1`](./tools/html_packager.ps1) nhúng ảnh Base64 tối ưu, bơm lớp vỏ đọc [`reader_shell.html`](./tools/reader_shell.html) (gồm nút chỉnh độ rộng `740px` bước `10px`, chuyển 3 chế độ màu Sáng / Dịu mắt / Tối, mục lục tự động, phóng to ảnh), kiểm định Auto-QA và xuất PDF.
  - [`src/extract_assets.py`](./tools/src/extract_assets.py) — Mã nguồn Python gốc dùng để biên dịch ra `extract_assets.exe` *(chỉ dùng tham khảo/build lại; khi chạy dịch thuật tuyệt đối không gọi Python hệ thống)*.
- `output/` — Thư mục chứa tệp đầu ra (`*_vi.html`, `*_vi.pdf`), tự động được tạo khi đóng gói và được bỏ qua bởi [`.gitignore`](./.gitignore).

## Giấy phép & Thành phần Bên thứ ba (License & Third-Party Notices)

- **Mã nguồn gốc của `luka-loop`:** Phần kịch bản điều phối Agent, Skill, script PowerShell, lớp vỏ [`tools/reader_shell.html`](./tools/reader_shell.html) và mã nguồn tự viết [`tools/src/extract_assets.py`](./tools/src/extract_assets.py) được cấp phép theo **MIT License** — xem chi tiết tại [`LICENSE`](./LICENSE).
- **Bộ công cụ thực thi dựng sẵn (`tools/extract_assets/`):** Bản đóng gói portable phân phối kèm trong kho lưu trữ có tích hợp các thành phần phần mềm bên thứ ba và chịu sự điều chỉnh của giấy phép tương ứng từng thành phần:
  - **PyMuPDF / MuPDF:** Cấp phép theo **AGPL-3.0**; toàn bộ mã nguồn tương ứng của công cụ tách ảnh được công khai đầy đủ tại [`tools/src/extract_assets.py`](./tools/src/extract_assets.py).
  - **Python 3.12.7:** Cấp phép theo **PSF License v2**.
  - **OpenSSL 3.0.15 (`libcrypto-3.dll`):** Cấp phép theo **Apache License 2.0**.
  - **PyInstaller:** Bootloader theo **GPL-2.0-or-later** (kèm *Bootloader Exception*) và runtime hooks theo **Apache License 2.0**.
  - **Microsoft Visual C++ Runtime / Universal CRT:** Thuộc bản quyền của Microsoft Corporation.

Vui lòng xem đầy đủ thông báo bản quyền và toàn văn các giấy phép bên thứ ba tại [`THIRD_PARTY_LICENSES.md`](./THIRD_PARTY_LICENSES.md) và thư mục [`licenses/`](./licenses/).

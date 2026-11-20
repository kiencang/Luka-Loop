# Hướng dẫn phát triển Luka-Loop

Tệp này dành cho người và AI agent khi **phát triển, sửa lỗi hoặc kiểm thử chính công cụ**. Khi dịch tài liệu, làm theo `AGENTS.md` và `SKILL.md`, không làm theo tệp này. Ở chế độ phát triển được phép đọc mã nguồn `tools\` và dùng Python hệ thống để build/test.

## Môi trường

- Windows 10/11 x64, Windows PowerShell 5.1 (có sẵn) và nên có PowerShell 7 (`pwsh`) để chạy test trên cả hai phiên bản như CI.
- Python **3.12.7** (khớp CI) và các gói ghim phiên bản: `python -m pip install -r tools\src\requirements-build.txt` (PyMuPDF, PyInstaller).
- Microsoft Edge hoặc Google Chrome để chạy các test xuất PDF thật.

## Cấu trúc mã

- `tools\src\` — mã nguồn Python của `extract_assets.exe`:
  - `extract_assets.py`: điểm vào CLI, phân luồng theo `--mode` (`extract`, `render-pages`, `crop-json`, `embed-images`, `html-to-pdf`).
  - `figure_detector.py`: tách hình/sơ đồ theo bố cục (pipeline 6 pha, ngưỡng gom trong `DetectorConfig`).
  - `image_ops.py`: render trang, cắt ảnh theo JSON, tối ưu ảnh.
  - Bước 4 (đóng gói), tách theo trách nhiệm — `packager.py` → `reader_shell.py`, `html_qa.py`, `pdf_export.py`, `output_paths.py` (không có vòng phụ thuộc):
    - `packager.py`: điểm vào `embed-images` — nhúng ảnh Base64 rồi điều phối các module dưới.
    - `reader_shell.py`: gắn `tools\reader_shell.html` (CSS, thanh công cụ, script), lấy script tin cậy, tiêm CSP.
    - `html_qa.py`: Auto-QA — bộ quét DOM & bảo mật một lượt (`_QADOMScanner`, `run_html_qa_check`).
    - `pdf_export.py`: điểm vào `html-to-pdf` — xuất PDF bằng Edge/Chrome headless cô lập.
    - `output_paths.py`: làm sạch tên tệp đầu ra, đánh số `_2`/`_3`, dọn `work\` sau khi đã có đầu ra.
  - `transcript.py`: tìm PDF đính kèm mới nhất trong `transcript.jsonl` (Antigravity `-TranscriptPath`).
  - `manifest.py`: in bản rút gọn `manifest.json` ra stdout (chỉ dùng thư viện chuẩn, không import module nào khác của dự án — bộ tách hình không phụ thuộc bộ đóng gói).
  - `path_guards.py`: kiểm tra an toàn đường dẫn (UNC, NTFS ADS, symlink/junction, tên thiết bị Windows), dọn `work\` an toàn.
- `tools\*.ps1` — wrapper PowerShell mỏng chuyển tiếp tham số vào exe; `tools\_path_guards.ps1` là tiện ích dùng chung.
- `tools\extract_assets\` — kết quả build (không đưa vào git; gói phát hành do CI build).
- Chỉ dẫn cho agent: `AGENTS.md`, `CLAUDE.md`, `.agents\skills\` (quy trình + SI dịch), `.agents\adapters\` (chi tiết riêng từng môi trường agent), `.claude\` (lối vào và quyền cho Claude Code).

## Build và test

```powershell
.\tools\build_extractor.ps1                 # build lại tools\extract_assets\extract_assets.exe
.\tests\run_tests.ps1 -IncludePython        # test PowerShell 5.1 + toàn bộ test Python
pwsh -NoProfile -File .\tests\run_tests.ps1 # test PowerShell 7
```

- **Build lại exe sau mọi thay đổi trong `tools\src\`** trước khi chạy test PowerShell: các wrapper và test PowerShell gọi exe, không gọi mã Python.
- Chạy nhanh riêng test Python: `$env:PYTHONUTF8='1'; python -m unittest discover -s tests -p "test_*.py"`.
- Ba tệp test chỉ cần thư viện chuẩn (không cần PyMuPDF/Edge): `test_skill_contracts.py`, `test_pdf_export_resilience.py`, `test_clean_dir_scope.py`.
- Test chỉ ghi vào thư mục tạm của hệ thống, không ghi vào `work\` hay `output\` của dự án.
- CI (`.github\workflows\ci.yml`) chạy khi đổi `tools/**`, `tests/**`, `.agents/**` hoặc `AGENTS.md`; quy trình phát hành (`release.yml`) chạy khi đẩy tag `v*`.

## Quy ước

- **Xuống dòng & mã hóa:** LF và UTF-8 cho mọi tệp văn bản (`.gitattributes`, `.editorconfig`); riêng `.cmd`/`.bat` dùng CRLF. Khi sửa tệp, giữ nguyên kiểu xuống dòng của tệp.
- **Chỉ dẫn cho agent:**
  - `AGENTS.md` và `SKILL.md` viết trung lập theo hành động ("đọc trọn 1 lần", "mở xem song song", "ghi nối dần"), không ghi tên công cụ của một agent cụ thể.
  - Chi tiết riêng của Antigravity chỉ đặt trong `.agents\adapters\antigravity.md`; riêng Claude Code trong `.agents\adapters\claude-code.md`.
  - `.claude\skills\` chỉ là lối vào: phần frontmatter (`name`, `description`) phải giống hệt skill gốc trong `.agents\skills\`.
  - Lệnh mẫu trong tài liệu bắt đầu đúng dạng `powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'tools\<script>.ps1'` để khớp quy tắc cho phép trong `.claude\settings.json`.
  - Sau mọi thay đổi ở các tệp này, chạy `test_skill_contracts.py`: test đối chiếu tham số, giá trị mặc định, dòng stdout, liên kết và kích thước tệp SI với mã thật.
- **Đổi dòng stdout của exe:** nếu `SKILL.md` dựa vào dòng đó, cập nhật `SKILL.md` cùng lúc (test đối chiếu sẽ báo nếu quên).
- **CHANGELOG:** ghi thay đổi vào mục `[Unreleased]`. Khi phát hành, đổi `[Unreleased]` thành số phiên bản, commit, rồi đẩy tag `vX.Y.Z` để CI build và đóng gói.
- **Commit:** tách theo chủ đề, tiêu đề tiếng Anh dạng `fix: …`, `feat: …`, `test: …`, `refactor: …`, `chore: …`, `docs: …`. Không commit `output\`, `work\`, `tools\extract_assets\`.

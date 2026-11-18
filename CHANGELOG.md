# Changelog

Tất cả những thay đổi đáng chú ý của dự án **luka-loop** sẽ được ghi lại trong file này.

## [1.1.1] - 2026-11-18
### Changed
- Đồng bộ chuẩn typography SKILL 1 (`pdf-to-html-vi\si_academic_html.md`) sang họ font `Inter` (fallback Windows `'Segoe UI'`), bật `tabular-nums` cho `table`, `'JetBrains Mono'` cho code và cập nhật thông báo font trong `THIRD_PARTY_LICENSES.md`;
- Bổ sung quy tắc trong `AGENTS.md` và cả 2 `SKILL.md` cấm chạy lệnh liệt kê/kiểm tra `output\` trước hoặc sau Bước 4 (tận dụng cơ chế tự tạo thư mục và tự đánh số `_2`, `_3` của `html_packager.ps1` để giảm lượt gọi thừa của Agent);
- Tinh gọn và đồng bộ 2 cặp tài liệu `SKILL` / `SI`: tỉa trùng lặp điều phối CLI khỏi `si_academic_html.md`, gỡ `@import` lặp ở `si_layout.md`, nối khít bước chuyển hóa tag trung gian + liên kết DOI/URL `References` giữa `si_translation.md` và `si_layout.md`, đồng thời bổ sung chốt chặn thực chiến (lọc tạp âm bản scan, chừa khoảng trắng quanh `<`/`>` trong LaTeX, lớp `.cjk`, `<header>` + `<article>` khớp `reader_shell.html`, `tr` + `.table-note` + `figure img { max-height: 82vh; }` an toàn in PDF).

## [1.1.0] - 2026-11-18
### Changed
- Tái cấu trúc `extract_assets.exe` tiếp nhận toàn bộ nghiệp vụ xử lý chính qua mô-đun `tools\src\path_guards.py` và `tools\src\html_packager_core.py`: kiểm tra an toàn đường dẫn/UNC/junction, phân giải PDF từ `transcript.jsonl`, tối ưu & nhúng Base64 trực tiếp trong bộ nhớ (không tạo ảnh tạm trên đĩa), Auto-QA HTML, bơm `reader_shell.html`, đánh số chống ghi đè, xuất PDF qua Edge/Chrome headless và dọn `work\`;
- Nâng cấp `PyMuPDF` từ `1.25.2` lên `1.28.2` trong `tools\src\requirements-build.txt` và bật lazy-import `_ensure_pymupdf()` (tắt thông báo gợi ý `pymupdf_layout` trên stdout để giữ đầu ra sạch);
- Rút gọn `tools\extract_pdf_assets.ps1`, `tools\pdf_fallback_tools.ps1` và `tools\html_packager.ps1` về dạng wrapper CLI siêu mỏng (51–85 dòng) giữ 100% tương thích tham số cũ, đồng bộ `.github\workflows\ci.yml` (`tools/src/*.py`), `build_extractor.ps1`, `SKILL.md`, `README.md`, `THIRD_PARTY_LICENSES.md` và bổ sung unit test trong `tests\test_extract_assets.py`.

## [1.0.8] - 2026-11-18
### Added
- Thiết lập GitHub Actions CI/CD (`.github\workflows\ci.yml` và `release.yml`): kiểm thử tự động trên **Windows PowerShell 5.1**, **PowerShell 7** và Python (cache binary theo mã băm nguồn khi push nhánh `main`), và build sạch `extract_assets.exe` khi đẩy tag `v*` để đóng gói trọn bộ `luka-loop-win-x64.zip` kèm `hashes.sha256` lên GitHub Releases;
- Thêm `tools\build_extractor.ps1` và tệp ghim phiên bản build `tools\src\requirements-build.txt` (`PyMuPDF==1.25.2`, `pyinstaller==6.20.0`).

### Changed
- Gỡ bỏ thư mục nhị phân `tools\extract_assets\` (58 tệp) khỏi theo dõi Git và thêm vào `.gitignore` để ngăn phình dung lượng lịch sử Git;
- Cập nhật `README.md` sang link tải 1-click trọn gói (`.../releases/latest/download/luka-loop-win-x64.zip`), đồng bộ `THIRD_PARTY_LICENSES.md` và bổ sung gợi ý tải/build trong `tools\_path_guards.ps1`.

## [1.0.7] - 2026-11-18
### Added
- Bổ sung 3 chế độ thuần PyMuPDF cho `extract_assets.py` / `extract_assets.exe` (`--mode render-pages`, `--mode crop-json`, `--mode optimize-images`) và gom hàm dùng chung `Resolve-SafeOutDirectory`, `Invoke-ExtractAssetsExe` vào `tools\_path_guards.ps1`;
- Mở rộng bộ kiểm thử `tests\test_extract_assets.py` (11 ca) và `tests\test_powershell.ps1` (13 ca): kiểm tra AST cấm API phụ thuộc GDI+/C# động/WinRT, hỗ trợ tự chạy theo `pwsh.exe` hoặc `powershell.exe`.

### Changed
- Hỗ trợ chạy song song trên cả **Windows PowerShell 5.1** lẫn **PowerShell 7+** (`pwsh.exe`): chuyển `tools\pdf_fallback_tools.ps1` và `tools\html_packager.ps1` sang gọi `extract_assets.exe`, loại bỏ hoàn toàn WinRT `Windows.Data.Pdf`, `System.Drawing` và `Add-Type` (kể cả trong `tests\test_powershell.ps1`);
- Tối ưu `html_packager.ps1`: khử trùng lặp ảnh cục bộ, xử lý theo lô 1 tiến trình duy nhất (bỏ qua nếu HTML có 0 ảnh), cập nhật build `extract_assets.exe` giữ nguyên quy mô 58 tệp (~56,5 MB) không thêm thư viện ngoài, và cập nhật `README.md`.
- Điều chỉnh SI dịch cho luồng bảo vệ định dạng;

### Fixed
- Bổ sung `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` vào `pdf_fallback_tools.ps1` và `html_packager.ps1` để không lỗi dấu đường dẫn tiếng Việt trên console `cp437`/`cp1252`;
- Sửa lỗi truyền `ConvertTo-Json` cho PowerShell 5.1 (`[pscustomobject]`), chuẩn hóa `--scale` theo `InvariantCulture`, và xử lý ngắt dòng `ConciseView` của PowerShell 7 trong `Invoke-CliPs1`.

## [1.0.6] - 2026-11-18
### Added
- Thêm skill `pdf-to-html-vi-layout` (chế độ bảo toàn thiết kế/layout): tách pha dịch `work\translated.md` (`si_translation.md`) trước khi dựng HTML/CSS cô lập từng trang (`si_layout.md`, font `Inter` `18px`, `--page-width` `740px–1000px`, CSS Multi-Columns/Grid);
- Thêm `-PreserveLayout` vào `tools\html_packager.ps1` (không tiêm `reader_shell.html`, cho phép `<table>` không bọc `.table-wrapper`) và 3 tệp PDF mẫu đa cột/bảng/scan tại `tests\layout_samples\`.

### Changed
- Phân tách hậu tố đầu ra `_vi.*` (mặc định) và `_layout_vi.*` (giữ thiết kế); `html_packager.ps1` luôn tự đánh số `_2`, `_3`... chống ghi đè đồng bộ cả cặp `.html`/`.pdf`;
- Cập nhật `AGENTS.md`, `README.md`, contract đầy đủ trong `SKILL.md` (chạy thẳng CLI, không đọc mã nguồn `tools\`) và ca kiểm thử tương ứng trong `tests\test_powershell.ps1`.

## [1.0.5] - 2026-11-18
### Added
- Bổ sung mục **Cách công cụ xử lý ảnh** kèm sơ đồ Mermaid tổng quan vào `README.md`;
- Bổ sung vào `manifest.json` các trường `dpi`, `source` (`raster`/`vector`/`hybrid`), `drawings`, `placement` (`figure`/`table_cell`) và ca kiểm thử tương ứng trong `tests\`;

### Changed
- Thay `bbox` PDF point bằng `box` chuẩn hóa `0.0–1.0` trong `manifest.json` (đồng bộ với `CropFromJson`) và build lại `extract_assets.exe` gọn nhẹ (58 tệp);
- Cập nhật `SKILL.md`, `si_academic_html.md` và `AGENTS.md`: quy tắc khai thác `manifest.json`, **Sàng lọc trước khi Cắt (`Triage before Crop`)** không cắt `CropFromJson` cho sơ đồ đơn giản (vẫn bắt buộc `read_file` song song ảnh đã tách), CSS ảnh ô bảng `td img`, và mẫu phản hồi kết quả thân thiện với người dùng cuối;

### Fixed
- Hỗ trợ nhận diện hàng bảng và trích `context` cho chữ căn giữa theo chiều dọc trong `extract_assets.py` (tránh bắt nhầm dòng tiêu đề bảng);
- Bổ sung `tests export-ignore` vào `.gitattributes` để loại bỏ cả thư mục `tests\` rỗng khỏi gói Release ZIP;

## [1.0.4] - 2026-11-17
### Added
- Thêm bộ kiểm thử tự động `tests\` (`run_tests.ps1`, `test_powershell.ps1`, `test_extract_assets.py`) kèm 3 tệp PDF mẫu (chuẩn, scan, hỗn hợp) và `.gitattributes` loại `tests\` khỏi gói Release ZIP;
- Bổ sung tham số `-Pages` cho `pdf_fallback_tools.ps1` (`RenderPages`) để chỉ render đúng các trang scan cần dùng;

### Changed
- Gom các hàm kiểm tra đường dẫn dùng chung sang `tools\_path_guards.ps1` và tối ưu phân tích ảnh bằng `LockBits` trong `html_packager.ps1`;
- Tương thích thư mục đồng bộ đám mây (OneDrive, Dropbox, Google Drive...): phân biệt symlink/junction thật với placeholder Cloud, cảnh báo tệp chưa tải offline và xử lý mềm khi khóa tệp lúc dọn `work\`;

### Fixed
- Sửa `extract_assets.py` và build lại `extract_assets.exe`: nhận diện đúng chú thích (`Fig. S1`, `Sơ đồ`, tránh văn xuôi bẫy), giữ nét nối lưu đồ & trục biểu đồ X/Y, giữ sơ đồ vector `>80` từ có chú thích, bỏ qua khung `<pre><code>`, hỗ trợ `CropBox`, PDF khóa mật khẩu và `stdout` UTF-8;
- Sửa Auto-QA `html_packager.ps1` (hỗ trợ nháy đơn, bỏ qua `\(`/`\[` trong `<pre>`/`<code>`), bật `PYTHONUTF8` & lọc `application/pdf` trong `extract_pdf_assets.ps1`, đọc ảnh không khóa file trong `pdf_fallback_tools.ps1` và đồng bộ `aria-hidden` ở `reader_shell.html`;

## [1.0.3] - 2026-11-17
### Fixed
- Cập nhật README.md rõ ràng hơn;
- Cập nhật để các file .ps1 an toàn và dự phòng lỗi tốt hơn;

## [1.0.2] - 2026-11-17
### Fixed
- README chi tiết hơn;
- Thông tin LICENSES chi tiết hơn;
- Cập nhật AGENTS.md để nó đồng bộ hơn với SKILL.md;

## [1.0.1] - 2026-11-17
### Fixed
- Điều chỉnh một chút CSS, và SI;

## [1.0.0] - 2026-11-16
### Fixed
- Điều chỉnh các vấn đề logic trong SKILL.md;

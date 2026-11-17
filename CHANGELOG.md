# Changelog

Tất cả những thay đổi đáng chú ý của dự án **luka-loop** sẽ được ghi lại trong file này.

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

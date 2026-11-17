# Changelog

Tất cả những thay đổi đáng chú ý của dự án **luka-loop** sẽ được ghi lại trong file này.

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

# Changelog

Tất cả những thay đổi đáng chú ý của dự án **luka-loop** sẽ được ghi lại trong file này.

## [1.1.5] - 2026-11-19
### Added
- Viết lại hoàn chỉnh `tools\src\figure_detector.py` theo kiến trúc **6 pha tuyến tính** (thuần PyMuPDF): tập trung cấu hình ngưỡng tại `DetectorConfig`, phân tích trang một lần vào `PageContext` (cache lazy `get_page_tables()`), phân loại minh bạch qua `FilterDecision(keep, reason)` và bổ sung API truy vết `detect_page_figures_debug(page)`;
- Tự động nới khung biểu đồ vector/hybrid để ôm trọn số chia trục, tiêu đề trục Y xoay 90° và tiêu đề trục X (`_expand_plot_axis_labels`), kèm nối dòng chú thích bị ngắt khối (`_merge_caption_continuations`) và hỗ trợ mẫu `Figure. A.7:`;
- Mở rộng bộ kiểm thử hồi quy tại `tests\test_extract_assets.py` (27 ca) và `tests\test_powershell.ps1` (14 ca) bao phủ toàn bộ 3 mẫu `tests\layout_samples\` và các tính năng mới của pipeline 6 pha.

### Changed
- Tinh chỉnh thuật toán ghép chú thích và gộp đa panel dựa trên đối chứng định lượng **4.999 trang IBM DocLayNet** (`scientific_articles` tăng IoU≥0.50 F1 từ `70.1%` lên `84.8%`, Loose F1 từ `79.3%` lên `91.6%` với Recall `98.3%`; toàn bộ 6 thể loại đạt IoU≥0.50 F1 `62.9%` / Loose F1 `68.7%`): ưu tiên chú thích trên/dưới hơn cạnh bên, áp dụng bất biến chống nuốt (`_violates_merge_invariants`) và bỏ xích gộp các khối không chú thích rời nhau.

### Fixed
- Khắc phục lỗi chia cắt đồ thị khoa học xếp chồng (không để số trục Y / tiêu đề trục xoay 90° bị nhận nhầm thành ô bảng, nhận diện nhãn toán/hóa học ngắn và cho phép dải sơ đồ ngang có chú thích `>= 18 pt`);
- Cứu biểu đồ vector vẽ nét nhỏ và heatmap nhiều ô ít chữ khỏi bị bộ lọc chữ vẽ nét (`outlined_glyph_confetti`) hoặc `find_tables()` loại nhầm;
- Loại sạch dương tính giả UI/bố cục hiện đại (Chrome/Skia/WeasyPrint): hộp bo góc nhiều đoạn Bézier, hero banner đầu trang, khung sidebar trái, thẻ giá/KPI có bullet căn cột + pill badge và bảng bo góc chứa `Table X` bên trong.

## [1.1.4] - 2026-11-19
### Added
- Gia cố bảo mật HTML/DOM trong `run_html_qa_check` (`tools\src\html_packager_core.py`): whitelist `<script>` (chỉ cho phép MathJax v3 CDN rỗng thân trong `<head>` và đúng mã `tools\reader_shell.html` khi không bật `-PreserveLayout`), chặn thẻ nhúng/chuyển hướng (`<iframe>`, `<object>`, `<embed>`, `<applet>`, `<base>`, `<form>`, `<meta http-equiv="refresh">`), thuộc tính `on*`/`srcdoc`/`ping`, URI nguy hiểm (`javascript:`, `vbscript:`, `file:`, `//...`, `data:` ngoài ảnh raster), ảnh/tài nguyên/CSS `url(...)` trỏ ra ngoài ngoài Google Fonts, và liệt kê cụ thể `src` ảnh lỗi;
- Lọc tên thiết bị dành riêng của Windows (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`) và tên kết thúc bằng dấu `.` trong `resolve_safe_crop_out_file` (`tools\src\path_guards.py`), kèm bộ kiểm thử bảo mật mới tại `tests\test_extract_assets.py` (25 ca) và `tests\test_powershell.ps1`.

### Changed
- Tách `tools\src\extract_assets.py` thành 3 module gọn (`extract_assets.py`, `figure_detector.py`, `image_ops.py`) vẫn đóng gói thành 1 tệp `extract_assets.exe` duy nhất (giữ nguyên lazy-import PyMuPDF); bỏ `onclick` và `src=""` mặc định trong `tools\reader_shell.html`; đồng bộ `SKILL.md`, `README.md` và `THIRD_PARTY_LICENSES.md`.

### Removed
- Gỡ bỏ chế độ CLI cũ không còn sử dụng `--mode optimize-images` (`optimize_images_batch`, `_optimize_single_image`) và hàm chết `_validate_bare_filename`.

## [1.1.3] - 2026-11-19
### Added
- Thu hồi các biểu đồ cột/thanh tách rời cạnh chú thích hình trong `tools\src\extract_assets.py` và mở rộng `tests\test_extract_assets.py` (từ 18 lên 24 ca) cho toàn bộ các ca bố cục, đồ thị và lọc nhiễu mới.

### Changed
- Nâng cấp ghép chú thích & đa khung hình trong `tools\src\extract_assets.py`: tách dòng qua ranh giới cột/giữa block, phân biệt chú thích với câu văn tham chiếu, hỗ trợ chú thích bên cạnh căn đáy, khoảng cách trên hình (`<= 64 pt`), cầu nối nhãn trục (`<= 78 pt`), phân xử chú thích hai phía, gộp nhiều subplot chung legend và giữ dải hình minh họa thấp trong ô bảng (`>= 16 pt`).

### Fixed
- Khắc phục sót đồ thị khoa học đa khung và biểu đồ phân tán nhiều điểm dấu (không để nhận nhầm biểu đồ có đường cong/chéo thành bảng và bảo vệ cụm có trục/khung dài);
- Lọc mạnh dương tính giả thực chiến: trang scan chia nhiều dải ngang, dải trang trí tràn lề, banner rộng đầu/cuối trang, watermark vector/raster dưới đoạn văn, thanh tiêu đề có chữ đè, cột bảng thưa chữ, bảng tài chính kẻ ngang không cột dọc và poster/công thức chữ vẽ nét `0`-từ.

## [1.1.2] - 2026-11-19
### Added
- Bổ sung mục **Cách công cụ giảm dung lượng ảnh** kèm sơ đồ Mermaid và tóm tắt 3 chốt bảo vệ vào `README.md`;
- Mở rộng `tests\test_extract_assets.py` (lên 18 ca) và `tests\test_powershell.ps1` cho các ca ảnh thang xám 8-bit, JPEG ít màu vượt `1400 px`, Auto-QA DOM/comment và kiểm tra junction nhánh ngoài workspace.

### Changed
- Nâng hệ số nén JPEG mặc định (`-JpegQuality` / `--quality`) từ `90` lên `95` đồng bộ trên `tools\html_packager.ps1`, `tools\src\html_packager_core.py`, `tools\src\extract_assets.py`, cả hai `SKILL.md` và bộ kiểm thử;
- Bổ sung quy tắc giới hạn phạm vi ghi tệp (`work\` / `output\` trong workspace) vào `AGENTS.md` và làm rõ chỉ thị xử lý liên tục tài liệu dài, đồng bộ mô tả Auto-QA mới trong cả hai `SKILL.md`.

### Fixed
- Sửa tối ưu ảnh trong `tools\src\extract_assets.py`: `_analyze_sample_grid` nhận diện ảnh thuần thang xám (`max-min <= 2`) để đếm đủ sắc độ 8-bit (`0..255`), và `_optimize_image_bytes` cho phép co kích thước JPEG ít màu vượt `MaxImageWidth` (`1400 px`) khi giúp giảm dung lượng;
- Thay kiểm tra regex phẳng trong `run_html_qa_check` (`tools\src\html_packager_core.py`) bằng `_QADOMScanner(HTMLParser)`: kiểm tra lồng thẻ `.table-wrapper` thực sự trên DOM, bỏ qua HTML comment (`<!-- ... -->`) và `<script>`/`<style>`/`<textarea>`, xử lý `<code>` lồng nhau, xác nhận MathJax `<script>` nằm trong `<head>`, đồng thời bỏ qua comment/raw blocks khi nhúng `<img>` và tiêm `reader_shell.html`;
- Sửa nhánh ngoài workspace của `assert_safe_output_path` (`tools\src\path_guards.py`) và `Assert-SafeOutputPath` (`tools\_path_guards.ps1`): bỏ `break` sớm để kiểm tra toàn bộ các thư mục tổ tiên tồn tại cho tới gốc ổ đĩa thay vì bỏ sót symlink/junction phía trên tệp hoặc thư mục con đã tồn tại.

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
